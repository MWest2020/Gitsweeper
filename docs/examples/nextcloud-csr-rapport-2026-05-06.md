# nextcloud/app-certificate-requests — procesrapport

**Peildatum:** 2026-05-06
**Dataset:** alle 1000 pull requests in
[`nextcloud/app-certificate-requests`](https://github.com/nextcloud/app-certificate-requests)
(volledige historie; de laatste pagina is pagina 10 bij 100 per
pagina).
**Conduction-slice:** de 22 pull requests van `MWest2020`.
**Tool:** [gitsweeper](../../README.md), v1 baseline.

---

## TL;DR voor Fabrice

1. **Het cert-request-proces is gezond op de typische case.** De
   mediaan time-to-merge is **1,65 dagen**; de mediaan tot eerste
   maintainer-reactie is **1,08 dagen**. 87% van de PRs die een
   beslissing nodig hebben krijgt die ook.

2. **De staart is wat schuurt.** 5% van de gemergde PRs duurt langer
   dan **16,8 dagen**; de slechtste legitieme case is **111,9 dagen**.
   Eén PR wachtte **273,9 dagen** op een eerste reactie. Dit zijn geen
   "het gemiddelde is langzaam"-getallen — het zijn individuele PRs
   die blijven hangen in een verder snel proces.

3. **Conduction's specifieke gap is reactie-snelheid, niet reactie-
   kwaliteit.** Onze PRs krijgen een reactie met dezelfde frequentie
   als de repo-norm (~80% vs 87%, niet significant op N=15), maar
   onze mediaan first-response is **3,59 dagen tegen 1,08 repo-breed**
   — ongeveer 3,3× langer. Het grootste deel van dat gat is
   "wachtrij-diepte bij batch-submissions" en geen afwijzing; zodra
   een maintainer er naar kijkt is de review-naar-merge-cyclus snel.

**Het meest actionable punt is punt 3.**

> **Korte samenvatting:** voor onze slice geldt dat er niet vaak genoeg
> gekeken wordt, maar zodra er wel gekeken wordt gaat het vrijwel
> direct goed en wordt het snel opgepikt. Het bottleneck is de
> wachtrij vóór de eerste blik, niet het werk daarna.

---

## Repo-overzicht

### Volume

| | aantal |
|---|---|
| Totaal PRs in historie | 1000 |
| Gemerged | 780 |
| Gesloten zonder merge | 193 |
| Nog open | 27 |

### Time-to-merge over gemergde PRs (dagen)

```
count   780
p25     0,26
median  1,65
p75     4,44
p95     16,81
max     111,93
mean    4,30   (≈ 2,6× de mediaan; rechts-scheve verdeling, dus
                gebruik de percentielen)
```

Het **gemiddelde** van 4,30 dagen is op zichzelf misleidend — het
wordt opgetrokken door een klein aantal stallen. De helft van alle
gemergde PRs landt binnen ~1,7 dagen, driekwart binnen ~4,4 dagen.
**Mediaan + p95** is de eerlijke samenvatting.

### Time-to-first-response (dagen)

"First response" is hier de eerste comment op de PR door iemand anders
dan de auteur. Van de 1000 PRs:

| | aantal |
|---|---|
| Kreeg een non-author comment | 787 |
| Nog geen non-author comment | 213 |

Van die 213 stille PRs:

| Categorie | aantal | Toelichting |
|---|---|---|
| **Self-pulled door indiener** | 100 | Indiener sloot de PR zelf (vaak een duplicate of snel-vervangen draft). Geen signaal over maintainer-engagement. |
| Stil gemerged | 89 | Maintainer mergede zonder comment — de reactie was de merge zelf. Telt als engagement. |
| Nog open | 19 | Wacht nog; uitkomst onbekend. |
| Door maintainer gesloten zonder comment | 3 | Echte stille afwijzingen — zeldzaam. |
| Onbekend | 2 | Events-API gaf geen duidelijke actor. |

Gecorrigeerd voor self-pulled en nog-open is de **maintainer
response-rate** op PRs die daadwerkelijk een beslissing nodig hadden:

```
787 met respons / (1000 − 100 self-pulled − 19 nog open)
= 787 / 881 ≈ 87 %
```

### Verdeling time-to-first-response (dagen)

```
count   787
p25     0,20
median  1,08
p75     3,92
p95     14,52
max     273,90
```

De 273,90-dagen-max is één uitschieter; het gros van de verdeling zit
onder de 4 dagen.

---

## Conduction-slice (`MWest2020`, 22 PRs)

### Volume

| | aantal |
|---|---|
| Totaal PRs van MWest2020 | 22 |
| Gemerged | 11 |
| Self-pulled (door indiener gesloten, geen maintainer-actie nodig) | 7 |
| Door maintainers gesloten zonder merge | 2 |
| Nog open | 2 |

De 7 self-pulled PRs zijn duplicates / vervangen submissions:

| Self-pulled | Vervangen door |
|---|---|
| #716, #717, #718, #719, #720 (binnen uren na aanmaak gesloten) | #721, #722, #723, #724 — alle gemerged |
| #727 | follow-up update op #725 (al gemerged) |
| #899 | #898 / #916 (gemerged) |

Deze tellen niet als maintainer-non-responsiveness en zitten niet in
de noemer van de response-rate hieronder.

### Time-to-merge over Conduction's 11 gemergde PRs (dagen)

```
count   11
p25     0,35
median  3,01
p75     5,20
p95     9,40
max     9,40
mean    3,62
```

De Conduction-verdeling is **smal** — geen stall-staart. De langzaamste
van onze merges (9,4 dagen, [#722](https://github.com/nextcloud/app-certificate-requests/pull/722))
zit ruim onder de p95 van de repo (16,8 dagen).

### Time-to-first-response over Conduction-PRs

Aangepaste noemer (exclusief self-pulled en nog-open):
22 − 7 − 2 = **15 PRs** waarover maintainers een beslissing moesten
nemen.

| | aantal | rate |
|---|---|---|
| Kreeg eerste maintainer-respons | 12 | 80% |
| Geen respons (1× stil gesloten door maintainer, 2× nog open) | 3 | 20% |

Dit is **in lijn met de repo-norm van 87%** binnen de ruis bij N=15.

```
count   12
median  3,59
mean    3,31
p25     2,22
p75     5,20
p95     5,97
max     5,97
```

Dit **wijkt wel** af van de repo-norm (mediaan 1,08 dagen).
Conduction-PRs wachten ongeveer **3,3× langer dan typisch** op de
eerste maintainer-comment.

### Wie reageert

| Maintainer | Conduction-PRs gereageerd op |
|---|---|
| `mgallien` | 5 |
| `camilasan` | 5 |
| `tobiasKaminsky` | 1 |
| `GretaD` | 1 |

Twee maintainers (`mgallien`, `camilasan`) doen 10 van de 12 reacties
op onze PRs. Dat is goed voor relatieopbouw; het is ook één punt van
latency wanneer beiden niet beschikbaar zijn.

### Op dit moment open Conduction-PRs

| # | Titel | Aangemaakt | Dagen open |
|---|---|---|---|
| [#996](https://github.com/nextcloud/app-certificate-requests/pull/996) | Update certificate request in opencatalogi.csr | 2026-04-27 | ~9 |
| [#997](https://github.com/nextcloud/app-certificate-requests/pull/997) | Update certificate request in openregister.csr | 2026-04-27 | ~9 |

Beide zitten onder de repo p95 (14,5 dagen) maar ruim boven de repo-
mediaan (1,1 dagen). Een `@mention` aan `mgallien` of `camilasan`
overwegen als ze niet binnenkort opgepakt worden.

---

## Waar het gat eigenlijk zit

**Time-to-merge na de eerste respons** (ruwe schatting uit
Conduction-data: mediaan TTM 3,0 dagen min mediaan first-response 3,6
dagen ≈ 0; veel Conduction-PRs worden gemerged op dezelfde dag als de
maintainer voor het eerst reageert). Dat is snel — **zodra er gekeken
wordt, sluit de PR**.

De bottleneck zit in de **wachttijd vóór de eerste blik**. En als je
het timing-patroon bekijkt (bv. #721–724 alle vier aangemaakt op
2024-08-31, alle vier op 2024-09-05 in dezelfde minuut beantwoord)
oogt de gap als een **batched-pickup-vertraging**: maintainers
verwerken onze submissions als groep in plaats van één voor één,
waardoor een batch van N PRs allemaal wachten op de pickup-tijd van
de langzaamste, niet de snelste.

---

## Concrete voorstellen voor het gesprek

1. **Niet vragen om "snellere merges".** De cyclus na engagement is
   al snel, en de mediaan time-to-merge voor Conduction (3,0 dagen)
   ligt twee dagen boven de repo-mediaan in een proces waarin
   vrijdag-tot-maandag-gaten al het meeste daarvan verklaren. Snel
   per ongeluk dichten, geen reëel voordeel.

2. **Wel vragen of een lichtgewicht pickup-signaal mogelijk is.** Een
   conventie als "@mention `mgallien` (of een `cert-request-team`-
   groep) wanneer een Conduction-batch klaar staat" zou onze
   response-mediaan waarschijnlijk van ~3,6 dagen naar de repo-norm
   van ~1,1 dagen brengen, zonder maintainer-load toe te voegen — ze
   reageren wanneer ze gepingd worden, op dit moment pakken ze het op
   in hun eigen poll-cadans.

3. **Aan onze kant: discipline tegen duplicate submissions.** Zeven
   van onze 22 PRs werden binnen uren self-gepulled, allemaal
   duplicates van andere PRs die we diezelfde dag hadden ingediend.
   Die ruis schaadt de review-ergonomie ("bedoelde je #898 of #899?")
   en laat onze slice slechter ogen dan ze is. Waarschijnlijk één
   workflow-aanpassing aan onze kant — één keer indienen, alleen
   opnieuw als er expliciet om gevraagd wordt.

---

## Methodologie en kanttekeningen

- **Bron:** GitHub REST API (`GET /repos/{owner}/{repo}/pulls?state=all`,
  gepagineerd). Comments uit
  `GET /repos/{owner}/{repo}/issues/{n}/comments`. Close-actor voor
  closed-without-merge PRs uit
  `GET /repos/{owner}/{repo}/issues/{n}/events` (de actor van de
  laatste `closed`-event).
- **"First response" is de eerste issue-comment door een non-author.**
  Dit telt **geen** formele PR-reviews (`APPROVE` /
  `REQUEST_CHANGES`) of regel-specifieke review-comments mee. Voor
  deze repository — een CSR-collectie waar review zeldzaam is en het
  meeste engagement via comments loopt — past de issue-comment-proxy
  bij de werkelijkheid, maar een maintainer die stil approve't via
  een review zonder comment lijkt in onze data "stil".
- **Self-pulled-detectie** gebruikt de close-event-actor; vangt het
  zeldzame geval niet waarin een indiener zijn eigen PR opruimt vanaf
  een ander account.
- **Time-to-merge** is wall-clock UTC (`merged_at - created_at`).
  Inclusief weekenden, feestdagen, review-back-and-forth.
- **Steekproefgrootte voor Conduction's 80% response-rate is 15 PRs.**
  Het verschil met de repo-norm van 87% valt ruim binnen de
  steekproefruis op een populatie zo klein.
- **Geen PR-review-state-data opgehaald**, dus PRs die wel een
  formele review-request-changes kregen maar geen comment, worden
  ten onrechte als "stil" geclassificeerd. Een handmatige steekproef
  suggereert dat dit voor deze repo zeldzaam is.

---

## Dit rapport reproduceren

```bash
export GITHUB_TOKEN=$(gh auth token)   # of een PAT met read:repo
gitsweeper fetch nextcloud/app-certificate-requests
gitsweeper throughput nextcloud/app-certificate-requests
gitsweeper throughput nextcloud/app-certificate-requests --since 2025-01-01
gitsweeper first-response nextcloud/app-certificate-requests
```

De Conduction-specifieke doorsneden en de close-actor-verrijking die
de "self-pulled vs maintainer-closed"-splitsing voedde waren one-off
SQL-queries tegen de lokale cache; deze zitten (nog) niet in de
gitsweeper-CLI.

---

*De Engelstalige versie van dit rapport staat in
[`nextcloud-csr-report-2026-05-06.md`](./nextcloud-csr-report-2026-05-06.md)
in dezelfde map.*
