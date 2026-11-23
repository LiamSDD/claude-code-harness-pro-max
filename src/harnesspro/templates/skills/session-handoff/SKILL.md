---
name: session-handoff
description: Write a precise handoff so the next session can continue without re-discovering context. Use before ending a session, when the context is nearly full, or when the user says "wrap up" or "hand off".
---

# Session handoff

The next session starts with an empty context. Everything it needs must be in files.

1. Make sure the work is in a coherent state: tests run, nothing half-edited. If something is half-done, say so explicitly.
2. Commit finished work. Leave unfinished work uncommitted only if you describe it.
3. Write the handoff note:

   ```bash
   harness progress note --heading "Handoff" "$(cat <<'NOTE'
   Done: <what is finished and verified>
   In progress: <file and function, what remains>
   Decisions: <choices made and why, so they are not re-litigated>
   Broken / risky: <failing tests, known bugs, hacks to remove>
   Next step: <the single next action, concrete enough to start immediately>
   NOTE
   )"
   ```

4. Update feature statuses with `harness progress start|done|block <id>`.
5. Tell the user in two or three sentences what state you left things in.

Never claim something works unless you ran it in this session.
