---
description: Fetch all unresolved review comments on the current branch's PR, triage them, then process each one iteratively with discussion before finalizing
---

# Fix Review Comments

## Phase 1: Fetch & Triage

### Step 1: Determine Repo and PR Number

First, get the current repository:

```bash
gh repo view --json nameWithOwner -q '.nameWithOwner'
```

Store this as REPO. Split it into OWNER and REPO_NAME.

Next, auto-detect the PR for the current branch:

```bash
gh pr view --json number -q '.number'
```

If this fails (no PR exists for the current branch), stop and tell the user:
> "No open PR found for the current branch. Please create a PR first and try again."

Store the resolved PR number as PR_NUMBER.

**Report to user:**
> **Configuration**
> - Repository: `OWNER/REPO_NAME`
> - PR: #PR_NUMBER

---

### Step 2: Fetch All Review Threads with Resolution State

Use GraphQL to get review threads with their `isResolved` status — this is the **only reliable way** to know if a thread is truly resolved (the REST API does not expose this):

```bash
gh api graphql --paginate -f query='
query($owner: String!, $repo: String!, $pr: Int!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100, after: $cursor) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          id
          isResolved
          path
          line
          comments(first: 100) {
            nodes {
              id
              databaseId
              author {
                login
              }
              body
              path
              line
              diffHunk
              url
              createdAt
            }
          }
        }
      }
    }
  }
}
' -f owner="OWNER" -f repo="REPO_NAME" -F pr=PR_NUMBER
```

From the results, build a structured list of threads:

For each thread:
- `thread_id` = the GraphQL node `id` (needed for resolving later)
- `is_resolved` = `isResolved` field
- `first_comment` = first item in `comments.nodes` (the original review comment)
- `replies` = remaining items in `comments.nodes`
- `author` = `first_comment.author.login`

### Filter to only unresolved threads:
- `is_resolved == false`

**Report to user:**
> **Fetch Results**
> - Total review threads on PR: X
> - Already resolved: Y
> - **Unresolved threads to process: N**

If N is 0, tell the user:
> "All review comments on this PR are already resolved! Nothing to do."

And stop.

---

### Step 3: Triage & Validate Each Comment

This is the critical step. For EACH unresolved comment, before making any changes:

#### 3a. Read the current file state

Read the file locally at the `path` specified in the comment. If the file doesn't exist locally, flag it and skip.

#### 3b. Check if the code has already changed

Compare the code in the `diffHunk` from the comment with the current local file content. If the code referenced in the comment no longer exists at that location (or anywhere in the file), the comment is **stale** and can be skipped.

#### 3c. Evaluate the feedback

For each comment, assess:

1. **Is the feedback technically correct?** — Does the concern actually apply? Is it a real bug, real test issue, real performance concern, or a false positive?
2. **Is the feedback still relevant?** — Has the code already been changed to address this? Did a later commit fix it?
3. **Does the feedback apply to the current code?** — Sometimes reviewers comment on an earlier commit and the code has since been refactored.
4. **Is there a reply in the thread that provides context?** — Check if the PR author or other reviewers replied with context that changes the assessment (e.g., "this is intentional", "singleton pattern", "the test actually passes").

#### 3d. Assign a confidence-scored verdict

For each comment, assign ONE of:

| Verdict | Confidence | Meaning | Planned Action |
|---------|------------|---------|----------------|
| VALID — WILL FIX | >80% confident the review is correct and actionable | Review is valid and actionable | Apply the fix |
| UNCERTAIN — NEEDS HUMAN | 50-80% either way | Could go either way | Flag for discussion |
| INVALID — WILL DISMISS | >80% confident the review does not apply | Review is a false positive | Dismiss with reply |
| STALE | N/A | Code has changed, comment no longer applies | Dismiss with reply |

#### 3e. Report the full triage to the user BEFORE proceeding

Present a detailed triage report:

> **Triage Report**
>
> **Comment 1/N** — `path/to/file.py` L42
> - Author: @username
> - Reviewer says: *(short summary of the feedback)*
> - Current code: *(show the relevant 3-5 lines from the local file)*
> - Assessment: *(your analysis of whether this is valid)*
> - Verdict: VALID — WILL FIX (95% confidence)
> - Planned action: Apply suggested code change / Implement fix for X

For **UNCERTAIN** comments, present actionable options:

> - Verdict: UNCERTAIN — NEEDS HUMAN (65% confidence)
> - Option A: Apply the fix — *(describe what the fix would be)*
> - Option B: Dismiss — *(describe why it might not apply)*
> - URL: *(comment URL for reference)*

Then show a summary:

> **Triage Summary**
> | Verdict | Count |
> |---------|-------|
> | VALID — WILL FIX | X |
> | UNCERTAIN — NEEDS HUMAN | Y |
> | INVALID — WILL DISMISS | Z |
> | STALE | W |

---

## Phase 2: Iterative Per-Comment Processing

After presenting the triage report, **stop and wait for user input**:

> "Review the triage above. You can override any verdict or discuss specific comments. When you're ready, say **start** to begin processing comments one by one."

### Ordering

Group comments by file path. Within each file, sort by line number. VALID and UNCERTAIN first, then INVALID and STALE.

---

### For VALID / UNCERTAIN comments (deep dive)

1. **Re-read the file** and show 10-15 lines of surrounding context.
2. **Present full analysis** with proposed fix.
3. **Stop and wait for user input.** The user can approve, suggest alternative, discuss, or skip.
4. Once agreed, **apply the fix locally.**
5. **Verify the change** — re-read the file, check surrounding code.
6. **Report the change.**

### For INVALID / STALE comments (quick confirm)

1. Re-present the triage entry.
2. Show the exact proposed reply text for GitHub.
3. **Stop and wait for user input.** The user can approve, edit, or skip.
4. Record the decision (no API calls yet).

### Progress indicator

> **Progress: 3/8 comments processed** (2 fixed, 1 will dismiss, 5 remaining)

### Pause support

User can say "pause" at any point. Present checkpoint summary and offer: (a) finalize what's done so far, or (b) exit with local changes only.

---

## Phase 3: Finalization

### 3a. Run Tests (Mandatory)

If any files were modified, detect and run tests automatically. If tests fail, pause for user input (adjust fix, revert, or proceed).

### 3b. Batch GitHub API Calls

#### Dismiss INVALID, STALE, and user-dismissed UNCERTAIN comments

Reply to comment:
```bash
gh api "repos/OWNER/REPO_NAME/pulls/PR_NUMBER/comments/COMMENT_DATABASE_ID/replies" \
  -X POST \
  -f body="REPLY_TEXT"
```

Resolve thread:
```bash
gh api graphql -f query='
mutation($threadId: ID!) {
  resolveReviewThread(input: {threadId: $threadId}) {
    thread {
      isResolved
    }
  }
}
' -f threadId="THREAD_NODE_ID"
```

#### Resolve fixed threads

For comments where a fix was applied — resolve the thread (no reply needed, the code change speaks for itself).

### 3c. Final Summary

> **Final Report — PR #PR_NUMBER**
>
> | # | File | Line(s) | Author | Feedback | Verdict | Action Taken |
> |---|------|---------|--------|----------|---------|--------------|
> | 1 | `file.py` | L42 | @user1 | Summary | VALID | Applied suggestion |
> | 2 | `other.py` | L100 | @user2 | Summary | INVALID | Dismissed with reply |
>
> **Stats:**
> - Fixed: X
> - Dismissed: Y
> - Skipped: Z
> - Stale (auto-resolved): W
>
> **Next steps:**
> 1. Review changes: `git diff`
> 2. Commit when ready
> 3. Push
