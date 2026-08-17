"""BAGIMSIZ/ATILABILIR test scripti - Ollama uzerinden calisan yerel modellerin
gercek 13 MCP aracini (bkz. src/mcp_server.py) dogru secip cagirabildigini,
yanit suresini ve Turkce yanit kalitesini olcer.

Bu dosya src/ altindaki HICBIR modul tarafindan import edilmez - sadece bir
kerelik deneme/karsilastirma araci; `src/llm_assistant.py`/`src/mcp_server.py`
UZERINDE HICBIR DEGISIKLIK gerektirmez (sadece SYSTEM_PROMPT/MCP_SERVER_SCRIPT/
PROJECT_ROOT/MAX_TOOL_ROUNDS sabitlerini oradan ICE AKTARIR - tek dogruluk
kaynagi/tutarli test icin, koklerini KOPYALAMAZ).

CALISTIRMADAN ONCE:
    1) Ollama kurulu ve servis calisir olmali (varsayilan http://localhost:11434).
       Windows'ta Ollama uygulamasini baslatmak veya `ollama list` gibi herhangi
       bir komut calistirmak servisi otomatik ayaga kaldirir.
    2) Test edilecek modeller cekilmis olmali:
           ollama pull qwen2.5:3b   (~2 GB indirme)
           ollama pull qwen2.5:7b   (~4.7 GB indirme)
    3) `ollama` Python paketi kurulu olmali (bu script icin, HENUZ requirements.txt'e
       eklenmedi - sadece bu deneme icindir):
           pip install ollama

CALISTIRMA:
    python scripts/test_ollama_tool_calling.py

Script, `Ollama servisine ulasilamiyor` veya `eksik model` durumunda NET bir
talimatla durur - sahte/varsayimsal cikti UYDURMAZ.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import ollama
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# `src/llm_assistant.py`'yi ice aktarabilmek icin src/'yi path'e ekle - bu script
# src/'nin BIR UST klasorundeki scripts/ altinda oldugundan, PROJECT_ROOT'u
# llm_assistant'in KENDISI hesaplamadan ONCE burada bagimsiz olarak turetmemiz
# gerekiyor (llm_assistant henuz import edilemedi).
_SCRIPT_DIR = Path(__file__).resolve().parent
_SRC_DIR = _SCRIPT_DIR.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# SYSTEM_PROMPT/MCP_SERVER_SCRIPT/PROJECT_ROOT/MAX_TOOL_ROUNDS KOPYALANMAZ, dogrudan
# ayni kaynaktan ice aktarilir - boylece bu test, uretim kodundan (chat_with_gemini'nin
# kullandigi ayarlardan) ASLA sapmaz.
from llm_assistant import (  # noqa: E402
    MAX_TOOL_ROUNDS,
    MCP_SERVER_SCRIPT,
    PROJECT_ROOT,
    SYSTEM_PROMPT,
)

SAMPLE_FILE_PATH = PROJECT_ROOT / "data" / "Turkcell Teknoloji 2026-08-07T17_21_57+0300.html"

# Kolayca yeni model eklenebilsin diye liste olarak tutulur.
MODELS_TO_TEST: list[str] = ["qwen2.5:3b", "qwen2.5:7b"]

# app/new_dashboard.py'deki SUGGESTED_QUESTIONS ile AYNI 4 soru + projeyle
# ILGISIZ bir soru ("Merhaba, nasılsın?") - bu sonuncusunda modelin HICBIR tool
# cagirmamasi, sistem promptundaki gibi dogal karsilik vermesi BEKLENEN (test
# edilen) davranistir.
TEST_QUESTIONS: list[str] = [
    "Kimin üzerinde kaç iş var?",
    "Hangi işler bloklu?",
    "Tahminlerimiz en çok nerede şaşıyor?",
    "En çok kaynak tüketen proje hangisi?",
    "Merhaba, nasılsın?",
]


def _mcp_tool_to_ollama_tool(tool) -> dict:
    """`llm_assistant._mcp_tool_to_gemini_declaration`'a PARALEL: `file_path`
    parametresini semadan cikarir (LLM'e hic gosterilmez, her cagriya otomatik
    enjekte edilir - bkz. `_run_ollama_tool_loop`), docstring'in ilk paragrafini
    aciklama yapar - ama Ollama'nin bekledigi `{"type": "function", "function":
    {...}}` sozlugunu uretir (Gemini'nin `FunctionDeclaration`'i yerine)."""
    schema = dict(tool.inputSchema or {})
    properties = dict(schema.get("properties", {}))
    properties.pop("file_path", None)
    required = [name for name in schema.get("required", []) if name != "file_path"]
    schema["properties"] = properties
    schema["required"] = required

    description = (tool.description or "").strip().split("\n\n")[0].strip()

    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": description,
            "parameters": schema,
        },
    }


async def _run_ollama_tool_loop(
    session: ClientSession,
    tool_names: set[str],
    ollama_tools: list[dict],
    file_path: str,
    model: str,
    user_message: str,
) -> tuple[str, list[str]]:
    """`llm_assistant._run_tool_loop` ile PARALEL bir tool-cagirma dongusu - ayni
    `MAX_TOOL_ROUNDS` siniri, ayni "file_path'i LLM'den gizle + her cagriya
    otomatik enjekte et" kurali. Donen `(nihai_metin, cagrilan_tool_adlari)`."""
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    called_tools: list[str] = []

    for _ in range(MAX_TOOL_ROUNDS):
        response = ollama.chat(model=model, messages=messages, tools=ollama_tools)
        message = response.message
        tool_calls = message.tool_calls or []

        if not tool_calls:
            return message.content or "Bir cevap üretemedim.", called_tools

        messages.append(
            {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {"function": {"name": tc.function.name, "arguments": dict(tc.function.arguments or {})}}
                    for tc in tool_calls
                ],
            }
        )

        for call in tool_calls:
            fn_name = call.function.name
            fn_args = dict(call.function.arguments or {})
            called_tools.append(fn_name)

            if fn_name in tool_names:
                fn_args["file_path"] = file_path  # LLM'in doldurmasina izin verilmez, gercek yol enjekte edilir
                try:
                    result = await session.call_tool(fn_name, fn_args)
                    text = "\n".join(c.text for c in result.content if hasattr(c, "text")) or "{}"
                except Exception as exc:  # noqa: BLE001 - arac hatasini modele geri bildir, sureci durdurma
                    text = json.dumps({"hata": str(exc)}, ensure_ascii=False)
            else:
                text = json.dumps({"hata": f"Bilinmeyen araç: {fn_name}"}, ensure_ascii=False)

            messages.append({"role": "tool", "content": text, "tool_name": fn_name})

    return (
        "Çok fazla araç çağrısı gerekti, net bir cevap üretemedim.",
        called_tools,
    )


async def _test_one(model: str, question: str, file_path: str) -> dict:
    """Bir (model, soru) cifti icin: `llm_assistant._chat_turn_async` ile AYNI
    sekilde `mcp_server.py`'yi bir alt surec olarak baslatip 13 araci kesfeder,
    tool-cagirma dongusunu calistirir, sureci kapatir. Toplam sureyi
    `time.perf_counter()` ile olcer."""
    server_params = StdioServerParameters(
        command=sys.executable, args=[str(MCP_SERVER_SCRIPT)], cwd=str(PROJECT_ROOT)
    )

    start = time.perf_counter()
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            mcp_tools = (await session.list_tools()).tools
            tool_names = {t.name for t in mcp_tools}
            ollama_tools = [_mcp_tool_to_ollama_tool(t) for t in mcp_tools]

            answer, called_tools = await _run_ollama_tool_loop(
                session, tool_names, ollama_tools, file_path, model, question
            )
    elapsed = time.perf_counter() - start

    return {"model": model, "question": question, "elapsed": elapsed, "tools": called_tools, "answer": answer}


def _check_ollama_ready(models: list[str]) -> None:
    """Ollama servisinin calisir durumda oldugunu VE gerekli modellerin cekilmis
    oldugunu dogrular; eksikse NET bir talimatla `sys.exit(1)` yapar - sahte/
    varsayimsal cikti UYDURMAK yerine kullaniciya ne yapmasi gerektigini soyler."""
    try:
        available = {m.model for m in ollama.list().models}
    except Exception as exc:  # noqa: BLE001 - kullaniciya anlasilir bir talimat vermek icin genis yakalama
        print(f"❌ Ollama servisine ulaşılamıyor ({exc}).")
        print("   Önce Ollama'nın çalıştığından emin olun (Ollama uygulamasını başlatın ya da")
        print("   'ollama serve' komutunu çalıştırın), sonra bu scripti tekrar çalıştırın.")
        sys.exit(1)

    missing = [m for m in models if m not in available]
    if missing:
        print(f"❌ Şu model(ler) Ollama'da bulunamadı: {', '.join(missing)}")
        for m in missing:
            print(f"   ollama pull {m}")
        print("   Yukarıdaki komut(lar)ı çalıştırıp modelleri çektikten sonra bu scripti tekrar çalıştırın.")
        sys.exit(1)

    if not SAMPLE_FILE_PATH.exists():
        print(f"❌ Örnek veri dosyası bulunamadı: {SAMPLE_FILE_PATH}")
        sys.exit(1)


def _print_summary_table(results: list[dict]) -> None:
    print("\n\n" + "=" * 110)
    print("ÖZET TABLO")
    print("=" * 110)
    header = f"{'Model':<13} {'Soru':<42} {'Süre (s)':>9}  {'Çağrılan Tool(lar)':<32} {'Yanıt Uzunluğu':>15}"
    print(header)
    print("-" * len(header))
    for r in results:
        soru_kisa = r["question"] if len(r["question"]) <= 40 else r["question"][:37] + "..."
        sure = f"{r['elapsed']:.2f}" if r["elapsed"] is not None else "HATA"
        tools_str = ", ".join(r["tools"]) if r["tools"] else "— (tool çağrılmadı)"
        if len(tools_str) > 30:
            tools_str = tools_str[:27] + "..."
        yanit_uzunlugu = len(r["answer"]) if r["answer"] else 0
        print(f"{r['model']:<13} {soru_kisa:<42} {sure:>9}  {tools_str:<32} {yanit_uzunlugu:>15}")
    print("=" * 110)


async def _main_async() -> None:
    results: list[dict] = []

    for model in MODELS_TO_TEST:
        for question in TEST_QUESTIONS:
            print(f"\n{'=' * 70}")
            print(f"Model : {model}")
            print(f"Soru  : {question}")
            print("=" * 70)
            try:
                result = await _test_one(model, question, str(SAMPLE_FILE_PATH))
            except Exception as exc:  # noqa: BLE001 - bir modelin/sorunun basarisiz olmasi tum testi durdurmasin
                print(f"HATA: {exc}")
                result = {"model": model, "question": question, "elapsed": None, "tools": [], "answer": f"[HATA] {exc}"}
            results.append(result)

            sure_str = f"{result['elapsed']:.2f} sn" if result["elapsed"] is not None else "N/A (hata)"
            print(f"Süre       : {sure_str}")
            print(f"Çağrılan   : {', '.join(result['tools']) if result['tools'] else 'Tool çağrılmadı'}")
            print(f"Yanıt      :\n{result['answer']}")

    _print_summary_table(results)


if __name__ == "__main__":
    print(f"Örnek veri dosyası: {SAMPLE_FILE_PATH}")
    print(f"Test edilecek modeller: {MODELS_TO_TEST}")
    print(f"Test soruları ({len(TEST_QUESTIONS)}): {TEST_QUESTIONS}\n")

    _check_ollama_ready(MODELS_TO_TEST)
    asyncio.run(_main_async())
