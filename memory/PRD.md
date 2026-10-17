# Mondo Noleggio (ChientiBike) – PRD

## Problema originale
App scaricabile da tutti per gestire la giacenza di bici a noleggio (gravel, e-bike, gravel muscolari): vedere disponibilità, prenotare per giorno/ora o più giorni, pagare. Ogni bici ha taglie S/M/L/XL in base all'altezza. App interamente in italiano.

## Scelte utente
- Pagamenti: Stripe (chiave test), Pagamento in negozio, PayPal (rimandato: servono Client ID/Secret sandbox)
- Login: email/password (JWT) + Google (Emergent)
- Area admin nell'app
- Prenotazione a ore e giornata/più giorni
- Nome: "Noleggio Nuovo", stile deciso dal designer (verde muschio, iOS clean)

## Architettura
- Backend FastAPI `/app/backend/server.py` + MongoDB (users, bikes, bookings, payment_transactions)
- Frontend Expo Router: (tabs) Bici / Prenotazioni / Profilo, bike/[id], checkout, payment-result, login, admin/index, admin/bike-form
- Disponibilità = stock taglia − prenotazioni sovrapposte (confermate o in attesa pagamento). Orari 9–19.

## Implementato (Giugno 2026)
- Catalogo con filtri categoria e taglia, dettaglio bici con selezione modalità/data/ora/durata/taglia e disponibilità live
- Prenotazione con pagamento Stripe Checkout o in negozio, schermata esito, riprova pagamento
- Le mie prenotazioni con annullamento e "Paga ora"
- Auth JWT + Google, admin seed (vedi test_credentials.md)
- Admin: statistiche, CRUD bici con stock per taglia, gestione prenotazioni (pagata, riconsegnata, annulla) con filtri
- Ripresa automatica della prenotazione dopo login
- Test backend 25/25 e flussi frontend superati

## Aggiornamenti
- App bilingue: italiano (predefinito) + inglese, selettore lingua nel Profilo, messaggi del server tradotti (Accept-Language)
- Solo noleggio giornaliero / più giorni (ritiro 9:00, riconsegna 19:00); noleggio a ore rimosso
- Categorie e prezzi: Gravel 40€, E-gravel 50€, E-bike MTB 60€ al giorno (prezzo auto nel form admin)
- Ogni bici: foto coerente, caratteristiche (telaio, motore, batteria, autonomia, escursione, cambio, freni, ruote, peso) e descrizione IT/EN, modificabili dall'admin
- Flotta reale: Raymon Soreno Comp (Gravel 40€), Raymon Norza Comp (E-gravel 50€), Raymon Vamok Pro (E-bike MTB Bosch CX 120 Nm, 800 Wh, 60€) con foto ufficiali e schede tecniche; quantità per taglia da confermare
- Sync foglio → app (sola lettura, ogni 2 min + pulsante "Sincronizza" in admin): stock per taglia dalla tabella flotta (16 unità EG/GR/EB), noleggi dal "Registro storico noleggi" importati come prenotazioni (source=sheet) che bloccano la disponibilità. File: backend/sheet_sync.py, env SHEET_ID/SHEET_GID
- Sync ogni 30s; scheda opzionale "Modelli" (Modello, Nome app, Categoria, Prezzo giorno, Foto, Descrizioni, specifiche) crea/aggiorna modelli; nuove righe flotta (XX-NNN … TG S/M/L/XL) aggiornano quantità; unità salvate in db.units
- Assegnazione automatica unità (es. GR-008) a ogni prenotazione app
- Scrittura app → foglio via Google Apps Script web app (backend/sheet_writer.py, env SHEET_SCRIPT_URL + SHEET_SCRIPT_TOKEN; script in memory/apps_script_modulo_noleggio.gs). In attesa che l'utente pubblichi lo script e fornisca l'URL

- App rinominata "Mondo Noleggio"; logo E-BIKE 4 ENDURO (ChientiBike) su icona, splash, favicon, header catalogo e login

## Backlog
- P0: Import/sync bici dal foglio Google "modulo noleggio" (serve accesso pubblico funzionante o file .csv/.xlsx)
- P0: PayPal (in attesa credenziali sandbox)
- P1: Upload foto bici (object storage) invece di URL; email di conferma prenotazione
- P1: Calendario disponibilità per admin, blocco bici in manutenzione
- P2: Codici sconto / pacchetti, recensioni, multi-negozio

## Update (fork)
- Public Apps Script code page: /api/codice (and /api/sheet-script/{token})
- Apps Script Web App URL linked & verified (ping OK), stored in db.meta sheet_write
- Booking confirmation email (Italian) via Emergent managed email: backend/mailer.py, sent once after store booking or Stripe paid; sender 'Mondo Noleggio', reply-to info@chientibike.it
- Shop notification email to SHOP_EMAIL (info@chientibike.it) per confirmed booking; pickup reminder email day before at 12:00 Europe/Rome (reminder_loop, every 10 min) with address Contrada Le Grazie 43 Tolentino (MC), tel 3289832243
- Google Sign-in (Emergent) already implemented & verified (button 'Continua con Google')
- 'Come arrivare' button (Google Maps directions) on home + bookings headers (src/components/DirectionsButton.tsx)
- Review request email day after return (12:00 Rome) with Google review link https://g.page/r/CRrkPKDBIM0oEBM/review
- WhatsApp 'Scrivici' button (wa.me/393289832243) next to 'Come arrivare' on home + bookings (ShopContactRow)
- 'Percorsi' tab (app/(tabs)/routes.tsx) with link to Strava profile https://www.strava.com/athletes/15242190 (user chose simple link, no API)
- Instagram button 'Seguici su Instagram' (instagram.com/chientibike) in Percorsi tab
- Removed size filter row from Home; Strava link changed to https://www.strava.com/athlete/routes (user request; private page, warned)
- Auto-enrich new sheet models (backend/enricher.py): Gemini 2.5 flash + googleSearch (EMERGENT_LLM_KEY) fills empty description IT/EN, specs and photo (og:image of product pages, brand site preferred); runs after sheet sync once per model (enriched_at); POST /api/admin/bikes/{id}/enrich to retry (fills only empty fields)
