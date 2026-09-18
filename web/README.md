# Web fallback

The page lives at [`core/static/index.html`](../core/static/index.html) and is
served by the API at `/`.

It was put there rather than deployed separately on purpose. It is one file
with no build step, it ships in the same container as everything else, and it
calls the API on its own origin — so there is no second deployment to keep in
sync, and no Vercel account in the critical path two days before submission.

It is plain HTML with no framework. If we want it on Vercel later the file
moves as is; only the `fetch` calls need an absolute API URL, and CORS would
have to be enabled on the API.

Open it at `http://<host>/`, or `http://<host>/?group=<group_id>` for a
different group.
