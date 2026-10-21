# Sample data

11 made-up Clawds (`projects.json`), their to-dos (`todo.json`) and a sample company / daily gossip (`settings.json`), in the same format as `data/db/`.
`server.py` copies these into `data/db/` the first time you start it, so the page is not empty. They are fictional characters; nothing here is anyone's real project.

- Start clean: `python clawd.py fresh`
- Bring them back: `python clawd.py fresh --sample` (`--en` for the English set in `db-en/`, same ids and structure, only the words differ; `CLAWDFIELD_SAMPLE_LANG=en` does the same for the first start)
