# 30-second demo — recording script

The story in one take: an agent gets **blocked** from doing something catastrophic, and the log
**proves** it — then a tampered log gets **caught**. That single arc is the whole pitch.

## Record it

Use [asciinema](https://asciinema.org) (`brew install asciinema`) then convert to GIF with
[agg](https://github.com/asciinema/agg), or just screen-record your terminal.

```bash
asciinema rec colorless.cast    # start recording; run the block below; Ctrl-D to stop
agg colorless.cast colorless.gif
```

## The exact commands to type (≈30s)

```bash
# 1. the agent runs a turn — one action is denied, one needs approval
python3 examples/agent_loop.py

# 2. independently verify the sealed record (this is the magic)
colorless verify agent.jsonl        # or: python3 -m colorless verify <the ledger path it printed>

# 3. now tamper with the log to hide the blocked action...
#    (edit one line — flip an "executed":false to true)
# 4. ...and watch verify catch it:
colorless verify agent.jsonl        # -> "ok": false, "reason": "entry payload altered"
```

> Tip: `examples/quickstart.py` already does the tamper step automatically and prints the
> before/after `verify()` — so for the tightest clip, just record `python3 examples/quickstart.py`.

## The caption to post with it

> AI agents can now move money, write code, and delete data. Two questions decide if you can
> ship them: can you **stop** the bad action, and can you **prove** what they did?
> `colorless` — gate + tamper-evident audit for every agent action. 5 lines, zero deps. [link]

## Narration beats (if you add voiceover)

1. "Here's an AI agent taking actions." (run)
2. "It tried to delete the database — blocked by policy. A $50k invoice — held for human approval." (point)
3. "Every action is sealed in a tamper-evident log." (`verify` → ok)
4. "Try to edit the log to cover it up —" (tamper)
5. "— and it's caught instantly." (`verify` → false)
