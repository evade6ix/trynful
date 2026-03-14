# Trynful Admin API + UI

This repo includes a zero-dependency Python backend (`http.server`) and static admin UI for event administration.

## Features

- Create/edit events with name, format, time controls, capacity, and registration window.
- Open/close registration.
- Add/remove participants manually.
- Start event, publish rounds, report overrides, finalize event.
- Audit log of admin actions (who, what, when).
- API role gating (`X-Role: admin`) and UI-level protections (buttons/forms disabled for non-admin role selection).

## Run

```bash
python app.py
```

Open `http://localhost:8000`.

## Tests

```bash
python -m unittest discover -s tests
```
