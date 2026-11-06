"""routing.dsn_led — ponte pcbnew (Python do KiCad) ↔ Freerouting.

Funções: exportar_dsn / importar_ses — chamadas pelo pipeline via subprocess
com o python3.9 do próprio KiCad (não o venv), pois precisa do módulo pcbnew.
Headless exige criar o wx.App ANTES de importar pcbnew (senão assert).
"""
import sys

try:
    import wx
    _app = wx.App(False)  # noqa: F841 — necessário para pcbnew headless
except ImportError:
    pass

import pcbnew


def main() -> int:
    comando = sys.argv[1]
    pcb_path = sys.argv[2]
    arquivo = sys.argv[3]

    board = pcbnew.LoadBoard(pcb_path)

    if comando == "export-dsn":
        ok = pcbnew.ExportSpecctraDSN(board, arquivo)
        print(f"DSN {'OK' if ok else 'FALHOU'} → {arquivo}")
        return 0 if ok else 1
    elif comando == "import-ses":
        ok = pcbnew.ImportSpecctraSES(board, arquivo)
        if ok:
            pcbnew.SaveBoard(pcb_path, board)
            print(f"SES aplicado e salvo → {pcb_path}")
            return 0
        print("ImportSpecctraSES falhou")
        return 1
    elif comando == "pads-json":
        import json

        dados = []
        for fp in board.GetFootprints():
            ref = fp.GetReference()
            for pad in list(fp.Pads()):
                p = pad.GetPosition()
                dados.append({"ref": ref, "pin": pad.GetPadName(),
                              "x": p.x / 1e6, "y": p.y / 1e6,
                              "net": pad.GetNetname() or None})
        with open(arquivo, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False)
        print(f"pads JSON OK ({len(dados)}) → {arquivo}")
        return 0
    else:
        print(f"comando desconhecido: {comando}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
