"""Extrae números de un texto en español (cifras y palabras) y arma los montos
que se pueden justificar con lo que dijo la usuaria. Sirve de guardia contra
montos inventados por el LLM."""
import re
import unicodedata
from itertools import combinations, permutations


def norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


UNITS = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
    "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17,
    "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiun": 21, "veintiuno": 21,
    "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25,
    "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
}
TENS = {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
        "setenta": 70, "ochenta": 80, "noventa": 90}
HUND = {"cien": 100, "ciento": 100, "doscientos": 200, "trescientos": 300,
        "cuatrocientos": 400, "quinientos": 500, "seiscientos": 600,
        "setecientos": 700, "ochocientos": 800, "novecientos": 900}


def numeros(texto):
    """Lista de números (en orden) que aparecen en el texto, en cifras o en letras."""
    toks = re.findall(r"\d+(?:[.,]\d+)?|[a-z]+", norm(texto))
    out, i, n = [], 0, len(toks)
    while i < n:
        t = toks[i]
        if t[0].isdigit():
            out.append(float(t.replace(",", ".")))
            i += 1
            continue
        val, j, found = 0, i, False
        if toks[j] in HUND:
            val += HUND[toks[j]]
            j += 1
            found = True
        if j < n and toks[j] in TENS:
            val += TENS[toks[j]]
            j += 1
            found = True
            if j + 1 < n and toks[j] == "y" and toks[j + 1] in UNITS and 1 <= UNITS[toks[j + 1]] <= 9:
                val += UNITS[toks[j + 1]]
                j += 2
        elif j < n and toks[j] in UNITS:
            val += UNITS[toks[j]]
            j += 1
            found = True
        if found:
            out.append(float(val))
            i = j
        else:
            i += 1
    return out


def candidatos(nums):
    """Montos que se pueden derivar de los números dichos: el número, productos,
    sumas, restas (descuentos), 'seis cincuenta' = 6.50 y a*b -/+ c."""
    c = set()

    def add(x):
        c.add(round(x, 2))

    nums = list(nums)
    for a, b in zip(nums, nums[1:]):  # "seis cincuenta" = 6.50
        if float(a).is_integer() and float(b).is_integer() and 10 <= b <= 99:
            nums.append(a + b / 100)
    for a in nums:
        add(a)
    for a, b in combinations(nums, 2):
        add(a * b)
        add(a + b)
        add(abs(a - b))
    if len(nums) <= 7:
        for a, b, d in permutations(nums, 3):
            add(a * b - d)
            add(a * b + d)
    return c


def grounded(monto, cands, extra=()):
    return any(abs(monto - x) < 0.011 for x in set(cands) | set(extra))
