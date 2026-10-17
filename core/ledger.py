"""Libro de movimientos de Doña Rosa: filas, fiados abiertos y recuerdo de cobros."""
import json
import re
from pathlib import Path

from .numbers import norm

_HON = {"don", "dona", "sr", "sra", "srta", "senor", "senora", "senorita", "la", "el"}


def cliente_key(c):
    return " ".join(t for t in re.findall(r"[a-z]+", norm(c or "")) if t not in _HON)


def _match(a, b):
    return a == b or bool(a and b and (a in b or b in a))


def _toks(s):
    return {t.rstrip("s") for t in re.findall(r"[a-z]+", norm(s)) if len(t) >= 4}


def _prod_match(a, b):
    return bool(_toks(a) & _toks(b))


class Ledger:
    def __init__(self, path=None):
        self.rows = []
        self._uid = 0
        self.path = Path(path) if path else None
        if self.path and self.path.exists():
            self._load()

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        self.rows = data.get("rows", [])
        self._uid = max([r["uid"] for r in self.rows], default=0)

    def save(self):
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"rows": self.rows}, ensure_ascii=False, indent=1), encoding="utf-8")

    def reset(self):
        self.rows, self._uid = [], 0
        self.save()

    def add(self, **row):
        self._uid += 1
        row["uid"] = self._uid
        row.setdefault("requiere_confirmacion", "SI" if row.get("monto") is None else "NO")
        row.setdefault("cliente", "")
        row.setdefault("dia", "")
        row.setdefault("id_mensaje", "")
        self.rows.append(row)
        self.save()
        return row

    def update(self, uid, **cambios):
        r = self.get(uid)
        if r is not None:
            r.update(cambios)
            self.save()
        return r

    def delete(self, uid):
        self.rows = [r for r in self.rows if r["uid"] != uid]
        self.save()

    def get(self, uid):
        return next((r for r in self.rows if r["uid"] == uid), None)

    def pendientes(self):
        return [r for r in self.rows if r["monto"] is None]

    def abiertos(self):
        """Fiados que aún no se cobran por completo (el cobro se descuenta en orden)."""
        entries = []
        for r in self.rows:
            k = cliente_key(r.get("cliente"))
            if r["tipo"] == "fiado":
                entries.append({"key": k, "cliente": r.get("cliente") or "", "producto": r["producto"],
                                "monto": r["monto"], "restante": r["monto"]})
            elif r["tipo"] == "cobro_fiado" and r["monto"] is not None:
                pay = r["monto"]
                for e in entries:
                    if pay <= 0.004:
                        break
                    if e["restante"] is None or e["restante"] <= 0.004:
                        continue
                    if k and not _match(k, e["key"]):
                        continue
                    take = min(e["restante"], pay)
                    e["restante"] = round(e["restante"] - take, 2)
                    pay -= take
        return [e for e in entries if e["restante"] is None or e["restante"] > 0.004]

    def recall(self, cliente, producto=""):
        """Monto que debe un cliente según lo ya registrado; None si no se puede saber."""
        k = cliente_key(cliente)
        ab = self.abiertos()
        cand = [e for e in ab if _match(k, e["key"])] if k else ab
        narrowed = False
        if producto:
            pf = [e for e in cand if _prod_match(producto, e["producto"])]
            if pf:
                cand, narrowed = pf, True
        if not k and not narrowed:
            return None
        if len(cand) > 1 and not narrowed:
            return None
        if not cand or any(e["restante"] is None for e in cand):
            return None
        return round(sum(e["restante"] for e in cand), 2)
