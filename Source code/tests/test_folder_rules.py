"""Macro folders and tags rules (mixin batch 3): names and tags tidied, the folder list, making / renaming /
removing a folder in the saved list, and the Edit filter. No windows, no settings file."""
import sys

src = sys.argv[1]
sys.path.insert(0, src)
import folder_rules as fr  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


# ---- names and tags
check("name: spaces tidied, control characters dropped", fr.clean_name("  Farm   day 2 ") == "Farm day 2"
      and fr.clean_name("a\tb\x00c\n") == "abc")
check("name: cut to the size", fr.clean_name("x" * 40) == "x" * 30 and fr.clean_name("abcdef", 3) == "abc")
check("name: nothing", fr.clean_name(None) == "" and fr.clean_name("   ") == "")
check("tags: split, lower case, no doubles", fr.clean_tags("AOT:R, rejoin #farm, Farm") == ["aot:r", "rejoin", "farm"])
check("tags: from a list", fr.clean_tags(["A", "b"]) == ["a", "b"])
check("tags: at most MAX_TAGS", len(fr.clean_tags(",".join(f"t{i}" for i in range(30)))) == fr.MAX_TAGS)
check("tags: a tag is cut to 20", fr.clean_tags("y" * 40) == ["y" * 20])
check("meta: checked", fr.clean_meta({"folder": " Farm ", "tags": "A"}) == {"folder": "Farm", "tags": ["a"]}
      and fr.clean_meta("junk") == {"folder": "", "tags": []})

# ---- the folder list
check("folders: made and in use, A to Z (any case), once", fr.folders(["b", "A", " b "], {"C", "", "A"}) == ["A", "b", "C"])
check("folders: a broken saved list", fr.folders("junk", {"x"}) == ["x"])

# ---- making a folder
made, shown = fr.add_folder(["Farm"], " Rejoin ", ["Farm"])
check("add: a new one", made == ["Farm", "Rejoin"] and shown == "Rejoin")
made, shown = fr.add_folder(["Farm"], "farm", ["Farm"])
check("add: one that's there (any case) isn't added again", made == ["Farm"] and shown == "Farm")
made, shown = fr.add_folder([], "used", ["Used"])
check("add: a folder a macro is in counts as there", made == [] and shown == "Used")
check("add: empty name", fr.add_folder(["a"], "  ", ["a"])[1] is None)
full = [f"f{i}" for i in range(fr.MAX_FOLDERS)]
check("add: no more than MAX_FOLDERS", fr.add_folder(full, "new", full)[1] is None
      and fr.add_folder(full, "f3", full)[1] == "f3")
check("add: a broken saved list", fr.add_folder("junk", "a", []) == (["a"], "a"))

# ---- renaming (bug fix batch 3: renaming to a name that was there saved it twice)
check("rename: the old name goes, the new one comes", fr.renamed(["Farm", "Other"], "Farm", "Rejoin") == ["Other", "Rejoin"])
check("rename: to a name that's there = once", fr.renamed(["Farm", "Rejoin"], "Farm", "Rejoin") == ["Rejoin"])
check("rename: to one there in another case = once", fr.renamed(["Farm", "rejoin"], "Farm", "Rejoin") == ["Rejoin"])
check("rename: to its own name = once", fr.renamed(["Farm"], "Farm", "Farm") == ["Farm"])
check("rename: a broken saved list", fr.renamed(None, "a", "b") == ["b"])

# ---- removing
check("remove: only that one", fr.removed(["Farm", " Farm ", "Other"], "Farm") == ["Other"])
check("remove: a broken saved list", fr.removed(5, "a") == [])

# ---- the Edit filter
meta = {"folder": "Daily", "tags": ["aot:r", "farm"]}
check("filter: empty = all", fr.matches("Blood", meta, "") and fr.matches("Blood", meta, None))
check("filter: in the name (any case)", fr.matches("Bloodawakening FINAL", meta, "final"))
check("filter: in the folder", fr.matches("x", meta, "dai"))
check("filter: in a tag", fr.matches("x", meta, "aot"))
check("filter: every word must be there", not fr.matches("Blood", meta, "blood rejoin"))
check("filter: #word = tags only", fr.matches("x", meta, "#far") and not fr.matches("farm", {"folder": "", "tags": []}, "#farm"))
check("filter: nothing there", not fr.matches("Blood", meta, "zzz"))

passed = sum(1 for _n, ok in results if ok)
print(f"\n{passed} of {len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
