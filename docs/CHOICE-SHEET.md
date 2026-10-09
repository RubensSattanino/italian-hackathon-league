# Choice sheet – Brambilla CRM

## 1. What we found in the data that the requests didn't say

**Case: Sales reps who left and were re-hired with a new account**
- **Where**: `utenti.csv` (`attivo`, `responsabile`), and the user references in `opportunita.csv.id_commerciale` and `ticket.csv.id_utente`.
- **How it's written**: `U72;Serena;Neri;serena.neri@…;Commerciale;U07;NO` next to `U80;Serena;Neri;s.neri@…;Commerciale;U04;SI`. The same happens for Marco Costa (U29/U81), Sara Colombo (U78/U82), Luca Santoro (U47/U83), Niccolò Bassi (U22/U84) and Mattia Panzeri (U65/U85).
- **How many rows**: 20 inactive users out of 85; 6 of them have an active "twin".
- **How we noticed**: we grouped users by name and found pairs with one account active and one inactive.

**Case: Sales rep written as a name instead of a code**
- **Where**: `opportunita.csv.id_commerciale`.
- **How it's written**: `D'AMICO NICCOLÒ`, `Mazza E.`, `T. Lombardo`, `Basile N.`, `paolo morelli`, alongside the usual `U41`.
- **How many rows**: about 120 rows; 687 rows are empty.
- **How we noticed**: the column has 201 distinct values but there are only 85 users.

**Case: VAT number hidden in the notes, in 6 formats**
- **Where**: `aziende.csv.note`.
- **How it's written**: `partita iva 84874 281912`, `P. IVA: IT 40969350707`, `p.iva IT11476373136`, `P.IVA 67105837370`, `PI: 34340014470`.
- **How many rows**: about 10,400 live companies.
- **How we noticed**: there is no VAT column, and R7 still requires the field.

**Case: Duplicate companies, by website or by VAT number**
- **Where**: `aziende.csv` (`sito_web`, `note`).
- **How it's written**: `www.nuovacablagginegri.it` and `https://nuovacablagginegri.it` are the same site. `dellavalleautomazionegroup.it` and `dellavalleautomazione.eu` are different sites with the same VAT number.
- **How many rows**: 19,698 live rows became 17,386 companies.
- **How we noticed**: we grouped rows by normalized domain and by VAT number. Same-name groups turned out to be different companies (different cities, sites and VAT numbers), so we do not merge by name.

**Case: Email and phone swapped**
- **Where**: `contatti.csv`.
- **How it's written**: `email=02/7222135`, `telefono=enrico.bassi@officinericci73.it`.
- **How many rows**: 125.

**Case: The same person without a usable email**
- **Where**: `contatti.csv`.
- **How it's written**: the same name, phone and company appear twice, one row with `nessuna` or `n.d.` and the other with a real email; or `irene.bellini @libero.it` (a space inside) and `x(at)gmail.com`.
- **How many rows**: about 220 groups by name and phone; 447 emails with a space inside; 489 written with `(at)`.

**Case: Monthly amounts on renewals ("I rinnovi sono annuali")**
- **Where**: `opportunita.csv.importo`, Rinnovi pipeline only.
- **How it's written**: `51.315,91 mensili`, `€ 2.100,00/mese`, `… al mese`.
- **How many rows**: 810.

**Case: Credit notes and reversals**
- **Where**: `opportunita.csv`.
- **How it's written**: `Storno fattura …`, `Nota di credito n. …`, `NC 615/24 …`, marked as won, with negative amounts written as `-x`, `x-` or `(x)`.
- **How many rows**: about 980.

**Case: Amounts in every format**
- **How it's written**: `€24,376.08`, `1.247.204,29`, `€206,5k`, `$ 772K`, `1,5 mln`, `EUR 4.5 k`.

**Case: Dates in 6 formats**
- **How it's written**: `dd/mm/yyyy`, ISO, `dd-mm-yyyy`, `dd.mm.yy`, `d/m/yyyy hh:mm`, and Excel serial numbers such as `45431`.

**Case: Won or lost deals without a close date**
- **Where**: `opportunita.csv.data_chiusura` together with `storico_fasi.csv`.
- **How we handled it**: the close date is the date the deal entered its final stage in the stage history.

**Case: Tickets without a contact but with a "Da: <email>" header**
- **Where**: `ticket.csv.descrizione`.
- **How many rows**: 456 tickets are linked to their contact this way.

**Case: Duplicate activities**
- **Where**: `attivita.csv`. The same type, date, text, contact and deal appear under two ids.
- **How many rows**: 10,316.

**Case: Discounts as fractions**
- **Where**: `righe_offerta.csv.sconto`.
- **How it's written**: `0,15` or `0.15` means 15%, next to `15`, `15%` and `15,0`. Quantities are written like `1 pz` or `197,2 m`.
- **Missing prices**: 2,761 lines have no unit price; they take the price-list price.

**Case: Price-list codes**
- **How it's written**: `BF38295`, ` BF-89712`, `bf-98503`, `BF. 123`. All become `BF-NNNNN`.

## 2. How we handled it and why
- **Sales reps who left**: the deal or ticket goes to the active twin account of the same person if there is one; otherwise it goes up the `responsabile` chain to the first active user. This follows the rule "chi ha lasciato l'azienda non segue più niente", and the data says who takes over. Activity authors (`autore`) keep the original writer.
- **Rep names**: matched to users with accents and case removed, as "first last", "last first", or initial plus surname; an active account is preferred.
- **Companies**: union-find on normalized domain and VAT number. The record kept is the most recently modified; each field takes the most recent non-empty value; the other domains go to `hs_additional_domains`.
- **Contacts**: emails are lowercased and spaces removed; `(at)` becomes `@`; values that are still invalid count as absent. Contacts are merged on the same email, or on the same first name, last name and phone when their emails do not conflict.
- **Amounts**: sign handling; `k`, `mila` and `mln` multipliers; monthly amounts ×12. Currency comes from `valuta`, then from the symbol in the amount, and defaults to EUR. A deal with quote lines takes the sum of its lines.
- **R8**: won deals (closedwon or Rinnovato) closed in 2025, converted to EUR (USD 0.92, GBP 1.17), credit notes included as negatives, total rounded to the cent.
- **R9**: a static list, `Clienti dormienti`, computed from the activities of the company's contacts and deals.

## 3. What we didn't do
- (to be filled in at 15:00)

## 4. The assistant
- **Model**: `openai/gpt-6-luna` on OpenRouter, with tool calling over 14 tools: search, get, associated records, create, update, associate, delete, pipelines, users, revenue, my customers, dormant customers, read attachment, apply price list.
- **How it writes**: through the same store functions as the API, so validation, the 409 on VAT numbers and the R10, R11 and R12 automations all apply.
- **Safety**: it refuses inactive users, duplicate VAT numbers and invalid emails. It asks when several records match, and it updates only the requested fields.
