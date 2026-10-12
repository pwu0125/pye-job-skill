#!/usr/bin/env python3
"""pye-job 批准标记链校验脚本（续跑判定的确定性依据，不靠肉眼扫标记）。

用法：
    python3 check_gate_status.py <项目根> [--slug <任务slug>]

输出 JSON：每个任务目录的各文档标记状态 + 该目录当前应进入的阶段。
阶段映射：spec.md→阶段一(闸门1)，plan.md→阶段二(闸门2)，task.md→阶段三(闸门3)，
checklist.md→阶段四(闸门4)；全部带 APPROVED 标记 → 阶段五/六。
PENDING-REVIEW 或无标记 → 该文档对应阶段需（重新）过闸。
S 级（只有一份 spec.md，其余三份不存在）→ 校验只查 spec.md（闸门 1/1）。
"""
import argparse
import json
import re
import sys
from pathlib import Path

DOCS = ["spec.md", "plan.md", "task.md", "checklist.md"]
STAGES = {"spec.md": 1, "plan.md": 2, "task.md": 3, "checklist.md": 4}
CN = {1: "一", 2: "二", 3: "三", 4: "四"}
MARKER = re.compile(r"<!--\s*pye-job:\s*(APPROVED|PENDING-REVIEW)\s*([^>]*)-->")


def read_marker(doc: Path):
    """返回 (状态, 标记行全文, 错误信息)；文件不存在返回 (None, None, 'missing')。"""
    if not doc.exists():
        return None, None, "missing"
    try:
        head = doc.read_text(encoding="utf-8", errors="replace")[:2000]
    except OSError as e:
        return None, None, f"unreadable: {e}"
    m = MARKER.search(head)
    if not m:
        return "NO-MARKER", None, None  # 无标记是有效检测态，不是读取错误
    return m.group(1), m.group(0).strip(), None


def judge(slug_dir: Path):
    """判定单个任务目录：各文档状态 + 应进入的阶段。"""
    docs, first_pending, all_approved, any_exists = {}, None, True, False
    s_level = False
    for name in DOCS:
        status, line, err = read_marker(slug_dir / name)
        docs[name] = {"status": status, "marker": line, "error": err}
        if err == "missing":
            continue
        any_exists = True
        if status != "APPROVED":
            all_approved = False
            if first_pending is None:
                first_pending = name
    if not any_exists:
        return docs, "阶段一", "空目录（四份文档都不存在），从阶段一开始"
    # S 级：只有 spec.md 存在（其余 missing）
    if docs["spec.md"]["error"] is None and all(
        docs[n]["error"] == "missing" for n in DOCS[1:]
    ):
        s_level = True
        if docs["spec.md"]["status"] == "APPROVED":
            return docs, "阶段五", "S 级 mini 文档已批准（闸门1/1），直接进开发"
        return docs, "阶段一", "S 级 mini 文档未批准，从阶段一开始"
    if all_approved:
        return docs, "阶段五", "四份文档全部 APPROVED，直接进阶段五/六"
    stage = STAGES[first_pending]
    return docs, f"阶段{CN[stage]}", f"首份未批准文档：{first_pending}，从阶段{CN[stage]}（闸门{stage}）继续"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", help="项目根目录（含 pye-job/）")
    ap.add_argument("--slug", default=None, help="只查指定任务子目录")
    args = ap.parse_args()
    pj = Path(args.root) / "pye-job"
    if not pj.is_dir():
        print(json.dumps({"error": f"no pye-job dir under {args.root}"}, ensure_ascii=False))
        return 1
    slugs = [d for d in sorted(pj.iterdir()) if d.is_dir()]
    if args.slug:
        slugs = [d for d in slugs if d.name == args.slug]
        if not slugs:
            print(json.dumps({"error": f"slug not found: {args.slug}"}, ensure_ascii=False))
            return 1
    out = {"root": str(pj), "tasks": []}
    for d in slugs:
        docs, stage, note = judge(d)
        out["tasks"].append({"slug": d.name, "stage": stage, "note": note, "docs": docs})
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
