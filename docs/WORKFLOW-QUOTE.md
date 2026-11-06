# WORKFLOW-QUOTE — receita de bolo: do pedido à placa na fábrica (Plano Mestre §14)

> **Regra de ouro**: nunca exportou Gerber com ERC/DRC ≠ 0. Em face simples,
> todo cruzamento é **conversado com você** (menu §4.3) — o pipeline
> **nunca decide sozinho**. Nada é inventado (§13.3): `needs_review` é o
> caminho honesto.

## 0. Instalar (uma vez)

```bash
./install.sh                     # mac/Linux — sem sudo; idempotente
powershell -ExecutionPolicy ByPass -File install.ps1   # Windows
```

Fim do instalador: `doctor` com **0 🔴**. A partir daí, sessão:

```bash
source scripts/env.sh            # PATH do venv + java
```

## 1. Descrever o que você quer (brain — M10)

```bash
python -m pcbforge.cli brain "quero uma placa blink: 1 led vermelho, \
  resistor pro led e conector 2 pinos de alimentação 5V, face simples"
```

O brain responde com a **prévia da netlist** + a lista honesta de perguntas
(`omitido`: alimentação? tamanho? conector? proteção? oscilador?…). Ele **não
inventa** componente faltante — você responde as perguntas que fizerem
sentido (responder por e-mail/painel) e/ou edita o netlist na tela.

Criar projeto direto da sugestão validada:

```bash
python -m pcbforge.cli brain "…pedido…" --criar minha-placa
```

## 2. Revisar no painel web (§13.1/§13.2)

```bash
python -m pcbforge.cli serve          # http://127.0.0.1:8000
```

- **netlist.json** e **board_profile.yaml** editáveis na tela; salvar só
  entra em disco com **validação viva** verde (PUT invalidado não salva);
- **seeds de placement** na tela (§4.3.2b): tabela seed × MST × sobreposições
  × cruzamentos — **você escolhe o seed** (o padrão do build é 5, os
  verdes provados do golden I03).

## 3. Build (31 s a alguns minutos, conforme a placa)

Botão **▶ Build** no painel (ou `python -m pcbforge.cli build minha-placa --seed 5`).
O `build.log` acompanha ao vivo; etapas: netlist → esquemático → PCB →
placement otimizado (§8, MST + anti-cruzamento) → Freerouting (loop com
seeds, DRC no loop) → ERC/DRC → export.

## 4. Se falhar (o painel conversa)

- **cruzamentos em face simples** → menu §4.3: **(a)** ponte 0Ω,
  **(b)** reorganizar placement (seed), **(c)** migrar p/ 2 camadas.
- **DRC bloqueador em tentativas seguintes** (neckdown fantasma etc.) →
  lista com pins exatos presos (§8, fallback_manual) + próximo seed.
- Seeds do golden I03 provadas verdes: **5 e 7**.

## 5. Revisar e fabricar

No painel: checklist pré-fab com **✅ em tudo** (`erc/drc/courtyard/catalogo/
zip/camadas`) → **⬇ baixar zip Gerbers**:

- prototipo: JLCPCB → *Add gerber file* → zip;
- montagem SMT (`assembly_jlcpcb: true`): no mesmo fluxo de upload — anexar
  `bom.csv` e `centroid.csv` (formato JLC pronto);
- conferir 3D/renders (`renders/top.png…` e `board.step`) antes de pagar.

## Fim a fim mínimo (sem GUI)

```bash
python -m pcbforge.cli new minha-placa --camadas 1
# … editar boards/minha-placa/design/* a mão …
python -m pcbforge.cli build minha-placa --seed 5
python -m pcbforge.cli checklist minha-placa
# zip: boards/minha-placa/outputs/minha-placa-v1-1c-<data>.zip
```
