# Noleggio Nuovo – PRD

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

## Backlog
- P0: PayPal (in attesa credenziali sandbox)
- P1: Upload foto bici (object storage) invece di URL; email di conferma prenotazione
- P1: Calendario disponibilità per admin, blocco bici in manutenzione
- P2: Codici sconto / pacchetti, recensioni, multi-negozio
