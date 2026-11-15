# medvital-link: the link to Earth

A Cloudflare Worker with a D1 database and Workers AI. The spacecraft hub sends its day-end batch and urgent
alerts here (`POST /outbox`), D1 keeps every record, and the NASA receiver pulls them (`GET /pull`).
Every route except `/health` needs the header `x-medvital-key`, checked against the secret `MEDVITAL_KEY`.

* Deployed from GitHub by Cloudflare (root directory `cloudflare`). Wrangler creates the `medvital` D1
  database on the first deploy and the Worker creates its tables on first use.
* Set the key once: Worker, Settings, Variables and Secrets, add a **secret** named `MEDVITAL_KEY`.
  Without it the Worker refuses every request.
* Run it locally: `python start.py --worker-local` at the repo root (local D1, no Workers AI).

See `docs/DECISIONS.md` D-035 for the full design.
