"""Tool tests. Offline checks always run; live Tavily checks run when
TAVILY_API_KEY is set (they cost ~4 Tavily credits of the free 1,000/month).

Run:  python scripts/test_tools.py
"""
import asyncio, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(HERE), ".env"))

from make_pdf import make_pdf
from core.tools.registry import Registry


def check(label, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    print("  [%s] %s%s" % (mark, label, (" -- " + str(detail)) if detail and not cond else ""))
    return bool(cond)


async def main():
    ok = True
    ws = tempfile.mkdtemp(prefix="argus_tools_")
    os.environ["ARGUS_WATCH_ROOT"] = ws
    os.environ.pop("ARGUS_ALLOW_SHELL", None)
    reg = Registry()
    call = reg.call

    print("=== discovery ===")
    # The baseline every build must have. Extra tools (e.g. `browse`, which needs
    # Playwright) are allowed and tested in their own suites, so adding one does
    # not break this gate.
    REQUIRED = {"fetch_url", "list_dir", "read_file", "shell", "tavily_search", "write_file"}
    ok &= check("required tools present", REQUIRED <= set(reg.tools),
                "missing: %s" % sorted(REQUIRED - set(reg.tools)))
    ok &= check("schemas are valid function defs",
                all(s["type"] == "function" and s["function"]["parameters"]["type"] == "object"
                    for s in reg.schemas()))
    ok &= check("dangerous flagged", reg.tools["write_file"].dangerous and reg.tools["shell"].dangerous)

    print("\n=== write / read round trip ===")
    r = await call("write_file", {"path": "notes/draft.md", "content": "# Hi\n\nline two\n"})
    ok &= check("write ok, creates folders", r.ok, r.summary)
    ok &= check("artifact path is absolute", os.path.isabs(r.meta.get("path", "")))
    r = await call("read_file", {"path": "notes/draft.md"})
    ok &= check("read back", r.ok and "line two" in r.detail, r.summary)
    r = await call("write_file", {"path": "notes/draft.md", "content": "more\n", "append": True})
    r = await call("read_file", {"path": "notes/draft.md"})
    ok &= check("append works", r.detail.endswith("more\n"))

    print("\n=== PDF ===")
    os.makedirs(os.path.join(ws, "refs"))
    make_pdf(os.path.join(ws, "refs", "paper.pdf"), "A Test Paper (2026)",
             ["Consistency-matched samplers reach FID 2.1 in four steps.",
              "This result supersedes the June baseline. " * 40])
    r = await call("read_file", {"path": "refs/paper.pdf"})
    ok &= check("pdf text extracted", r.ok and "FID 2.1" in r.detail, r.summary)
    ok &= check("pdf page count reported", r.meta.get("pages", 0) >= 1, r.meta)
    print("    " + r.summary)

    print("\n=== list_dir ===")
    os.makedirs(os.path.join(ws, "node_modules", "junk"))
    r = await call("list_dir", {})
    ok &= check("lists files with sizes", r.ok and "paper.pdf" in r.detail and "KB" in r.detail,
                r.detail)
    ok &= check("skips node_modules", "node_modules" not in r.detail)
    print("    " + r.detail.replace("\n", "\n    "))

    print("\n=== workspace confinement (the important part) ===")
    outside = tempfile.mkdtemp(prefix="argus_outside_")
    secret = os.path.join(outside, "secret.txt")
    open(secret, "w").write("do not read")
    attempts = [
        ("read_file", {"path": secret}),
        ("read_file", {"path": "../" + os.path.basename(outside) + "/secret.txt"}),
        ("read_file", {"path": "..\\..\\..\\Windows\\win.ini"}),
        ("read_file", {"path": "C:/Windows/win.ini"}),
        ("write_file", {"path": "../escaped.txt", "content": "x"}),
        ("write_file", {"path": os.path.join(outside, "planted.txt"), "content": "x"}),
        ("list_dir", {"path": ".."}),
        ("read_file", {"path": "D:/anything.txt"}),
    ]
    for name, args in attempts:
        r = await call(name, args)
        ok &= check("refused: %s %s" % (name, args["path"][-40:]), not r.ok, r.summary)
    ok &= check("nothing planted outside", not os.path.exists(os.path.join(outside, "planted.txt")))
    ok &= check("nothing escaped upward",
                not os.path.exists(os.path.join(os.path.dirname(ws), "escaped.txt")))

    print("\n=== shell is opt-in ===")
    r = await call("shell", {"command": "echo hi"})
    ok &= check("disabled by default", not r.ok and "disabled" in r.summary, r.summary)
    os.environ["ARGUS_ALLOW_SHELL"] = "1"
    r = await call("shell", {"command": "echo argus-ok"})
    ok &= check("runs when enabled", r.ok and "argus-ok" in r.detail, r.summary)
    os.environ.pop("ARGUS_ALLOW_SHELL")

    print("\n=== bad input never raises ===")
    for name, args in [("read_file", {"path": "missing.txt"}), ("fetch_url", {"url": "file:///etc/passwd"}),
                       ("tavily_search", {"query": ""}), ("list_dir", {"path": "nope"})]:
        r = await call(name, args)
        ok &= check("%s %s -> ok=False" % (name, list(args.values())[0]), not r.ok, r.summary)

    if os.environ.get("TAVILY_API_KEY"):
        print("\n=== live Tavily ===")
        r = await call("tavily_search", {"query": "NVIDIA Nemotron 3 Ultra release", "max_results": 5})
        ok &= check("search ok", r.ok, r.summary)
        cites = r.meta.get("citations", [])
        ok &= check("numbered citations", cites and cites[0]["n"] == 1 and cites[0]["url"].startswith("http"))
        ok &= check("no duplicate urls", len({c["url"] for c in cites}) == len(cites))
        print("    " + r.summary)
        for c in cites[:5]:
            print("    [%d] %s -- %s" % (c["n"], c["title"][:60], c["domain"]))
        if cites:
            r = await call("fetch_url", {"url": cites[0]["url"]})
            ok &= check("fetch top source", r.ok and len(r.detail) > 200, r.summary)
            print("    " + r.summary + " via " + str(r.meta.get("via")))
    else:
        print("\n(skipping live Tavily: no TAVILY_API_KEY)")

    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
