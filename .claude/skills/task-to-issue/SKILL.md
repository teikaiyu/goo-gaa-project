### Skill: `task-to-issue` (Atomic Issue Breakdown Specialist)

#### Description:
`PROBLEM.md` のタスクや検証事項を受け取り、指示者がコードの意図を完全に理解しながら1ステップずつ実装できるよう、極小単位（15〜30分で完結する作業粒度）の Issue 構成案を生成する。

#### Execution Instructions:
1. 指定されたタスクを「一度に1つのことだけを変更・検証する最小単位」に分解すること。
2. 出力する Issue には必ず以下のセクションを含めること:
   - **Why (目的・背景)**: なぜこの作業が必要か、アーキテクチャのどこに位置するか。
   - **What (変更内容)**: どのファイルをどのように追加・編集するか。
   - **Acceptance Criteria (完了条件)**: 何をもって「動作した」と判定するか（テストコマンドや実行結果の例）。
   - **Learning Tip (学びのポイント)**: 実装を通じて開発者が学べる低レイヤやPythonの知識。
3. **注意**: 指示者の許可がない限り、GitHub API等を使って直接リモートリポジトリに Issue を作成してはならない。Markdown形式でのテキスト出力にとどめること。

#### Issue Template Output Format:
```markdown
## Issue: [モジュール名] 簡潔なタスク名

### 1. Why (背景と目的)
- 

### 2. Scope & Target Files
- 対象ファイル: `path/to/file.py`
- 変更内容: 

### 3. Step-by-Step Implementation Guide
1. 
2. 

### 4. Acceptance Criteria (完了の定義)
- [ ] `python xxx.py` を実行した際、〇〇が出力されること
- [ ] CPU使用率・メモリリーク等の異常がないこと

### 5. Learning Checkpoint (理解すべき概念)
-
