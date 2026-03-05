# Azure Configuration

## Teacher Accounts

- **56 teachers** total: 40 Lausanne (In Person) + 16 Online
- UPN format: `firstname.lastname@swisslearninggroup.onmicrosoft.com`
- License: Office 365 A1 for faculty (SKU: `STANDARDWOFFPACK_FACULTY`)
- Temp passwords stored in `reports/provision_*.json`

## App Registration

App ID: `63a2f848-ceb5-497f-aed2-3936893c3247`

| Permission (Application) | Purpose |
|--------------------------|---------|
| `User.Read.All` | Read tenant users |
| `User.ReadWrite.All` | Create users + assign licenses |
| `Organization.Read.All` | Read subscribed SKUs (license lookup) |
| `Calendars.ReadWrite` | Create/delete events on teacher calendars |
| `Files.Read.All` | Read SharePoint Excel (teacher directory) |
| `Tasks.ReadWrite.All` | Create/update Planner tasks (used by UI app) |
| `AuditLog.Read.All` | Sign-in activity (requires Azure AD Premium — not available) |
| `Reports.Read.All` | Office 365 usage reports |

## Key Identifiers

| Resource | ID |
|----------|-----|
| A1 Faculty License SKU | `94763226-9b3c-4e75-a931-5c89701abe66` |
| Microsoft 365 Group | `3e1567b2-40ad-4ab3-b91c-ac9a12062b0c` |
| SharePoint Drive ID | `b!RBattyx0GEKBlUMx4h6grijjsEzWaIpPozUrzEG1hTpuS2MIEC8DS58MqVXPuQzG` |
| SharePoint Item ID | `01LPNJR5PKQDWVLKVPOJD3LEPWI3LEL45P` |
