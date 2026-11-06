---
name: threejs
description: "Use when building 3D scenes with Three.js — scene/camera/WebGLRenderer setup, setAnimationLoop and resize handling, geometries, PBR materials and lights, loading glTF with GLTFLoader plus DRACOLoader/KTX2Loader, color management and tone mapping, raycasting, instancing, disposing GPU resources, WebGPURenderer, and React Three Fiber."
license: MIT
---

# Three.js

Set up Three.js scenes that look right (correct color space, PBR lighting), load real assets
(compressed glTF), and stay fast (few draw calls, no GPU memory leaks). Written against the
current `three` npm release (r186 / `0.186.x`); check `THREE.REVISION` in the project.

## When to Use This Skill
- Adding a 3D viewer, product configurator, or background scene to a web app
- Loading `.glb`/`.gltf` models, HDR environments, or KTX2 textures
- Models look washed out, too dark, or the wrong colors
- Frame rate drops, or memory grows when navigating between views
- Picking objects with the mouse, or rendering thousands of copies of a mesh

## Setup
```bash
npm i three
npm i -D @types/three   # TypeScript; match the three minor version
```
```ts
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const canvas = document.querySelector<HTMLCanvasElement>('#scene')!;
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping; // or AgXToneMapping / NeutralToneMapping
// outputColorSpace defaults to SRGBColorSpace; ColorManagement is on by default.

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 100); // tight near/far avoids z-fighting
camera.position.set(3, 2, 5);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;

function resize() {
  const { clientWidth: w, clientHeight: h } = canvas;
  const dpr = renderer.getPixelRatio();
  if (canvas.width !== Math.floor(w * dpr) || canvas.height !== Math.floor(h * dpr)) {
    renderer.setSize(w, h, false); // false: let CSS own the element size
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
}

const timer = new THREE.Timer(); // THREE.Clock is deprecated since r183
renderer.setAnimationLoop((time) => {
  timer.update(time);
  resize();
  controls.update(timer.getDelta());
  renderer.render(scene, camera);
});
```
- Import add-ons from `three/addons/...` (maps to `examples/jsm`). Never mix two copies of
  `three` (e.g. a CDN build plus npm) — `instanceof` checks break silently.
- Use `setAnimationLoop`, not a hand-rolled `requestAnimationFrame`; it is required for WebXR.
- If nothing animates, render on demand (`controls.addEventListener('change', render)`).

## Materials, lights, and color
- Default to `MeshStandardMaterial` (metalness/roughness). `MeshPhysicalMaterial` adds
  clearcoat, transmission, sheen — costlier. `MeshBasicMaterial` ignores lights.
- Lights use physical units (the legacy lighting mode was removed). An environment map gives
  the biggest realism win for PBR:
```ts
import { HDRLoader } from 'three/addons/loaders/HDRLoader.js'; // RGBELoader is deprecated (r180)

const hdr = await new HDRLoader().loadAsync('/env/studio_1k.hdr');
hdr.mapping = THREE.EquirectangularReflectionMapping;
scene.environment = hdr;          // lights PBR materials
scene.background = new THREE.Color(0x111111);
```
- Color textures (albedo/baseColor, emissive) need `texture.colorSpace = THREE.SRGBColorSpace`.
  Data textures (normal, roughness, metalness, AO) stay linear (the default). GLTFLoader sets
  this for you; manual `TextureLoader` loads do not.
- Shadows: `renderer.shadowMap.enabled = true`, `light.castShadow`, `mesh.castShadow` /
  `receiveShadow`, and keep the shadow camera frustum tight around the scene.

## Loading glTF
glTF/GLB is the format to use. Compress geometry with Draco or Meshopt and textures with KTX2.
```ts
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { KTX2Loader } from 'three/addons/loaders/KTX2Loader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';

const draco = new DRACOLoader().setDecoderPath('/decoders/draco/');   // copy of examples/jsm/libs/draco/
const ktx2 = new KTX2Loader().setTranscoderPath('/decoders/basis/').detectSupport(renderer);
const loader = new GLTFLoader().setDRACOLoader(draco).setKTX2Loader(ktx2).setMeshoptDecoder(MeshoptDecoder);

const gltf = await loader.loadAsync('/models/chair.glb');
scene.add(gltf.scene);
const mixer = gltf.animations.length ? new THREE.AnimationMixer(gltf.scene) : null;
gltf.animations.forEach((clip) => mixer!.clipAction(clip).play());
// in the loop: mixer?.update(delta)
```
- Copy the decoder files from `node_modules/three/examples/jsm/libs/{draco,basis}/` into your
  public folder at build time so their version matches `three`.
- Optimize assets offline: `npx @gltf-transform/cli optimize in.glb out.glb --texture-compress ktx2`.

## Performance
| Problem | Fix |
|---------|-----|
| Many identical meshes | `InstancedMesh` (one draw call) with `setMatrixAt` + `instanceMatrix.needsUpdate = true` |
| Many different static meshes | Merge with `BufferGeometryUtils.mergeGeometries` or `BatchedMesh` |
| High-DPI GPU load | Cap pixel ratio at 2; lower it while interacting |
| Large textures | KTX2/Basis, power-of-two sizes, ≤ 2048 px for most assets |
| Heavy post-processing | Fewer passes; render at lower resolution |

Watch `renderer.info.render.calls` and `renderer.info.memory` — draw calls usually matter
more than triangle count.

**Disposal:** removing an object from the scene does not free GPU memory.
```ts
function disposeObject(root: THREE.Object3D) {
  root.traverse((obj) => {
    if (!(obj instanceof THREE.Mesh)) return;
    obj.geometry.dispose();
    for (const m of [obj.material].flat()) {
      for (const v of Object.values(m)) if (v instanceof THREE.Texture) v.dispose();
      m.dispose();
    }
  });
}
// on teardown: disposeObject(scene); controls.dispose(); renderer.setAnimationLoop(null); renderer.dispose();
```

## Raycasting
```ts
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
canvas.addEventListener('pointerdown', (e) => {
  const r = canvas.getBoundingClientRect();
  pointer.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  raycaster.setFromCamera(pointer, camera);
  const [hit] = raycaster.intersectObjects(pickables, true); // test a list, not the whole scene
  if (hit) select(hit.object, hit.point);
});
```
For `InstancedMesh`, `hit.instanceId` identifies the instance. For big meshes, add
`three-mesh-bvh` to accelerate raycasts.

## WebGPU and React
- `WebGPURenderer` (`import * as THREE from 'three/webgpu'`) falls back to WebGL 2 and uses TSL
  node materials instead of `ShaderMaterial`/`onBeforeCompile`. Pick it for new projects that
  need compute or TSL; keep `WebGLRenderer` when relying on GLSL shaders or older add-ons.
- In React use React Three Fiber (`@react-three/fiber`, v9 for React 19) and `@react-three/drei`.
  R3F manages the loop, resize, and disposal of objects it creates; never call
  `setState` inside `useFrame` — mutate refs instead.

## Rules
- Set `colorSpace = SRGBColorSpace` on every manually loaded color texture; leave data maps linear.
- Dispose geometries, materials, textures, and render targets you create; nothing is GC'd on the GPU.
- Cap `devicePixelRatio` at 2 and keep near/far planes as tight as the scene allows.
- Reuse geometries and materials across meshes; never create them inside the render loop.
- Ship glTF with compressed geometry and textures; never ship raw FBX/OBJ to production.

## Common Mistakes
- Model is black → no lights and no `scene.environment`; `MeshStandardMaterial` needs light.
- Washed-out or too-dark colors → wrong texture color space or custom shader skipping the
  `colorspace_fragment` / tone mapping chunks.
- Canvas is blurry or stretched → `setSize` not called on resize, or `camera.updateProjectionMatrix()` forgotten.
- `DRACOLoader: Failed to load decoder` → decoder path wrong or files not deployed.
- Memory climbs on route changes → no disposal and the animation loop still running.

## Verify
- Check `renderer.info.render.calls` and FPS (`stats.js` from `three/addons/libs/stats.module.js`).
- Navigate away and back several times; `renderer.info.memory.geometries/textures` must return to baseline.
- Compare a model against the glTF Sample Viewer render to confirm color and lighting.
- Run `npx @gltf-transform/cli inspect model.glb` to confirm compression and texture sizes.


---

*Instalada a partir de opencodeskills.dev (MIT) — corpo original preservado; créditos mantidos por exigência da licença MIT.*
