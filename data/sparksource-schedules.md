# SparkSource Schedule & Calendar Reference

**Source**: SparkSource ERP (`slc.sparksource.fr`)
**Last updated**: 2026-02-25
**Recon method**: Playwright automation of `/ffdates/week/booking` agenda dropdown

## How It Works

SparkSource organizes class schedules into **agendas** — one per school/type/location combination. Each agenda is a separate booking grid showing rooms, time slots, and teacher assignments for one week at a time.

The agenda is selected via a `<select name="set_agenda">` dropdown on the weekly booking page. Changing it POSTs to `/ffdates/set_agenda` and reloads the grid.

Teacher names are **not** in the grid cells — they must be fetched per activity from `/ffdates/list_attendees/{activity_id}/`.

---

## Complete Agenda Directory

### Lausanne

| ID | Agenda Label | Type | Notes |
|----|-------------|------|-------|
| **16** | Master Lausanne | - | Not used yet |
| **17** | SFS Lausanne | Method | French method classes (encounters + workshops) |
| **18** | ESA Lausanne | Method | German method classes (encounters + workshops) |
| **57** | Private English | VIP/Private | Private English lessons |
| **100** | Private French | VIP/Private | Private French lessons |
| **101** | Private German | VIP/Private | Private German lessons |
| **135** | Reception Team | Internal | Admin/reception scheduling, not student-facing |

### Geneva

| ID | Agenda Label | Type | Notes |
|----|-------------|------|-------|
| **12** | SFS Geneva | Method | English method classes |
| **13** | ESA Geneva | Method | German method classes |
| **48** | Private Classes | VIP/Private | All languages combined (not split like Lausanne) |
| **122** | Juniors | Junior | Junior programs |

### Fribourg

| ID | Agenda Label | Type | Notes |
|----|-------------|------|-------|
| **20** | SFS Fribourg | Method | English method classes |
| **21** | ESA Fribourg | Method | German method classes |
| **19** | In company | In Company | Corporate/on-site training |
| **108** | English Classes | Other | Separate English program (not SFS method) |
| **125** | Ville de Fribourg | Corporate | Municipal contract |
| **126** | Accueil scolaire | Corporate | School integration program |
| **129** | ORS | Corporate | ORS contract |
| **130** | Liebherr | Corporate | Liebherr corporate training |

### Montreux

| ID | Agenda Label | Type | Notes |
|----|-------------|------|-------|
| **33** | SFS | Method | English method classes |
| **34** | ESA | Method | German method classes |
| **110** | VIP WSE | VIP/Private | WSE private lessons |
| **111** | VIP ESA | VIP/Private | ESA private lessons |
| **112** | VIP SFS | VIP/Private | SFS private lessons |
| **32** | SFSI - in companies | In Company | Corporate/on-site training |
| **127** | Junior ESA | Junior | German junior programs |
| **128** | Junior WSE | Junior | WSE junior programs |

---

## Organization by Type

### Method Classes (Regular Group)

Standard school program — students attend scheduled encounters (1-on-1 or small group) and workshops (level-based group classes).

| Location | School | Agenda ID |
|----------|--------|-----------|
| Lausanne | SFS (English) | 17 |
| Lausanne | ESA (German) | 18 |
| Geneva | SFS (English) | 12 |
| Geneva | ESA (German) | 13 |
| Fribourg | SFS (English) | 20 |
| Fribourg | ESA (German) | 21 |
| Montreux | SFS (English) | 33 |
| Montreux | ESA (German) | 34 |

**Activity types found in method agendas** (from SFS Lausanne recon):

| Type | Code Pattern | Example | Typical Size |
|------|-------------|---------|-------------|
| Encounter | `E01`-`E54` | "Echange 13" | 1-5 students |
| Workshop | `A2`, `B2` | Level-named | 7-8 students |
| Social Club | `SCL` | "Social Club" | ~26 students |
| Induction | `IND` | "Induction" | 1 student |
| Service Time | (empty) | "Service Time" | 0 (internal) |

### VIP / Private Lessons (VAD)

Individual or semi-private paid courses. In Lausanne these are split by language; other locations group differently.

| Location | Agenda Label | Agenda ID | Split by |
|----------|-------------|-----------|----------|
| Lausanne | Private English | 57 | Language |
| Lausanne | Private French | 100 | Language |
| Lausanne | Private German | 101 | Language |
| Geneva | Private Classes | 48 | All languages combined |
| Montreux | VIP WSE | 110 | School |
| Montreux | VIP ESA | 111 | School |
| Montreux | VIP SFS | 112 | School |

**Fribourg**: No dedicated private/VIP agenda visible — may be handled within the method agendas or the "English Classes" (108) agenda.

### In Company (TCP)

Corporate training delivered on-site at the client's premises.

| Location | Agenda Label | Agenda ID |
|----------|-------------|-----------|
| Fribourg | In company | 19 |
| Montreux | SFSI - in companies | 32 |

**Lausanne & Geneva**: No dedicated in-company agendas visible — likely managed outside SparkSource or within method agendas.

**Fribourg corporate contracts** (dedicated agendas per client):

| Client | Agenda ID |
|--------|-----------|
| Ville de Fribourg | 125 |
| Accueil scolaire | 126 |
| ORS | 129 |
| Liebherr | 130 |

### Junior Programs (JPR)

Programs for younger learners.

| Location | Agenda Label | Agenda ID |
|----------|-------------|-----------|
| Geneva | Juniors | 122 |
| Montreux | Junior ESA | 127 |
| Montreux | Junior WSE | 128 |

**Lausanne & Fribourg**: No dedicated junior agendas visible.

### Other / Uncategorized

| Location | Agenda Label | Agenda ID | Purpose |
|----------|-------------|-----------|---------|
| Lausanne | Master Lausanne | 16 | Overview/combined view |
| Lausanne | Reception Team | 135 | Internal admin scheduling |
| Fribourg | English Classes | 108 | Separate English program (not SFS method) |

---

## Organization by School

### SFS (Swiss French School) — English

| Location | Method | VIP/Private | In Company | Junior |
|----------|--------|-------------|------------|--------|
| Lausanne | 17 | 57 (English) | — | — |
| Geneva | 12 | 48 (shared) | — | — |
| Fribourg | 20 | — | 19 | — |
| Montreux | 33 | 112 | 32 | — |

### ESA (European School of Arts?) — German

| Location | Method | VIP/Private | In Company | Junior |
|----------|--------|-------------|------------|--------|
| Lausanne | 18 | 101 (German) | — | — |
| Geneva | 13 | 48 (shared) | — | — |
| Fribourg | 21 | — | — | — |
| Montreux | 34 | 111 | — | 127 |

### WSE (Wall Street English)

| Location | Method | VIP/Private | In Company | Junior |
|----------|--------|-------------|------------|--------|
| Montreux | — | 110 | — | 128 |

**Note**: WSE has no dedicated method agendas visible in SparkSource. WSE method class scheduling may be handled differently or not yet set up in the booking system.

---

## Scraping Status

### Completed (Lausanne)

| Agenda | Key | Teachers | Slots | Date |
|--------|-----|----------|-------|------|
| SFS Lausanne (17) | `sfs_lausanne` | 20 | 69 | 2026-02-23 |
| ESA Lausanne (18) | `esa_lausanne` | 15 | 55 | 2026-02-23 |
| Private English (57) | `private_english_lausanne` | 12 | 55 | 2026-02-25 |
| Private French (100) | `private_french_lausanne` | 19 | 88 | 2026-02-25 |
| Private German (101) | `private_german_lausanne` | 12 | 84 | 2026-02-25 |

**Total across 5 Lausanne agendas: 48 unique teachers, 351 slots**

Output files in `data/`:
- `teacher-schedule-sfs_lausanne.json`
- `teacher-schedule-esa_lausanne.json`
- `teacher-schedule-private_english_lausanne.json`
- `teacher-schedule-private_french_lausanne.json`
- `teacher-schedule-private_german_lausanne.json`

### Teacher Overlap: Method vs Private

Many teachers teach both method (SFS/ESA) and private classes. Their Outlook calendars must reflect **both** to avoid double-booking.

| Overlap | Count | Detail |
|---------|-------|--------|
| SFS/ESA + Private French | 17 of 19 | Nearly all Private French teachers also teach SFS method |
| SFS/ESA + Private German | 12 of 12 | ALL Private German teachers also teach ESA method |
| SFS/ESA + Private English | 0 of 12 | Dedicated VIP English pool — no overlap with method |

**Key insight**: Private English has its own dedicated teacher pool (12 teachers who don't appear in any method agenda). Private French and German are taught by the same teachers who do SFS/ESA method classes — their private slots are **additional** busy time on top of their method schedules.

When syncing to Outlook calendars, the `sync_calendars.py` script must merge slots from **all** agendas a teacher appears in.

### Not Yet Scraped

| Agenda | ID | Priority | Notes |
|--------|----|----------|-------|
| Private Classes (Geneva) | 48 | Medium | Single agenda for all languages |
| VIP WSE (Montreux) | 110 | Medium | |
| VIP ESA (Montreux) | 111 | Medium | |
| VIP SFS (Montreux) | 112 | Medium | |
| All method agendas (Geneva, Fribourg, Montreux) | various | Low | Only needed if matching expands beyond Lausanne |
| Junior, In Company, Corporate | various | Low | Not relevant to current VIP matching |

---

## Scraper Configuration

The scraper uses agenda keys mapped to IDs in `schedule.py` (Student Follow Up project):

```python
AGENDA_IDS = {
    # Method classes
    "sfs_lausanne": "17",
    "esa_lausanne": "18",
    "sfs_geneva": "12",
    "esa_geneva": "13",
    "sfs_fribourg": "20",
    "esa_fribourg": "21",
    "sfs_montreux": "33",
    "esa_montreux": "34",
    # Private / VIP — Lausanne (split by language)
    "private_english_lausanne": "57",
    "private_french_lausanne": "100",
    "private_german_lausanne": "101",
}
```

**To scrape a new agenda**, add its key/ID to `AGENDA_IDS` and run:

```bash
cd "C:\Users\zackg\OneDrive\Desktop\AI Projects\Student Follow Up"
uv run python scripts/get_daily_schedule.py --weekly-teachers --agenda <key>
```

Output: `data/teacher-schedule-<key>.json`

### Keys to add for future scraping

```python
# Geneva / Montreux private agendas (not yet added)
"private_geneva": "48",
"vip_wse_montreux": "110",
"vip_esa_montreux": "111",
"vip_sfs_montreux": "112",
```

---

## VIP Program Types (from UI form)

The Streamlit VIP intake form offers these program types (from the Excel template dropdown):

- Exam Prep
- Private Method 2 Units a week
- Private Method 1 Unit a week
- Private Method 2 Units a month
- Intensive Traditional
- Specific Needs
- Junior VIP
- Interview Prep
- Other

Schools: SFS, ESA, WSE, None, Multiple Schools
Course delivery: In person, Online, In company
Dynamic: Group, Private, Semi-private
