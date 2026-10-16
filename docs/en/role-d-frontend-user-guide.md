# GigMate frontend user guide

## API delivery update (2026-10-17)

New-order and lifecycle operations now follow server capability flags; unsupported controls are hidden. The business-management extension is prepared for PR32 but stays absent until the server advertises completed security acceptance. See the [API inventory and release conditions](role-d-api-audit.md).

Current delivery candidate · 2026-10-16. [中文手册](../zh/role-d-frontend-user-guide.md) · [Acceptance and limits](role-d-final-acceptance.md).

## 1 Current pages and capability

The candidate follows merged #26/#27/main `71de8d9`. There is one business service, blank login fields and no public password, sample-input button or environment switch. Old `/environments/...` bookmarks stop at an explicit retired-entry page; open `/` only after checking the configured service. Existing records and WhatsApp sessions are not deleted or converted.

| Page | What you can do |
| --- | --- |
| Business | Search existing orders, read linked source revisions, accept supported time/date-only/address proposals and use reviewed status commands |
| New order | Select an authorized conversation, fill missing/known details, choose customer evidence, review and save through the merged C contract |
| Reply approvals | Review exact recipient/body/source/expiry/versions; approve, reject/cancel, reissue and inspect history |
| Calendar and tasks | Month view, all-appointment list, date keyboard navigation, full-account tasks, owned confirmed appointment `.ics` downloads |
| Manual review | Read processing diagnostics, distinguish historical rounds, inspect original conversation and open linked orders |
| WhatsApp | Connect/authorize conversations, read messages and attachments, use the separate explicitly authorized sending gateway |
| Features and help | See what is available and why a particular function remains disabled |

A blank list is not an error and not proof that AI understood everything. Production onboarding, real model activation and the complete business send loop remain team dependencies.

## 2 Open the workspace

Use the GigMate account provided by the maintainer. It is separate from your WhatsApp account. Do not enter your phone password here. The delivery page never displays development credentials.

For local development, start your already-configured backend without resetting its database or session. In `apps/web`, macOS/Linux:

```bash
GIGMATE_REAL_API_URL=http://127.0.0.1:18702 npm run dev
```

PowerShell:

```powershell
$env:GIGMATE_REAL_API_URL = 'http://127.0.0.1:18702'
npm run dev
```

Use your actual backend port and the printed frontend URL. The backend must allow that frontend origin. The old default-environment/isolated/alias variables no longer select a service. Delivery assets always request same-origin `/api/v1`; the development proxy forwards only the GigMate session cookie. Private provider configuration is never placed in the page. Test resources are prepared externally by developers, never selected in the product.

### Frontend tests and building

Use pinned Node 24.15.0/npm 11.12.1 and the project Python 3.12.10 environment. Each checkout needs `.venv/bin/python` (POSIX) or `.venv/Scripts/python.exe` (Windows); an explicit `GIGMATE_TEST_PYTHON` is also supported. Missing Python fails clearly instead of skipping tests.

```bash
npm ci
npm run check:api
npm run format:check
npm run build
```

`build` runs tests and compiles. `bundle` only typechecks/compiles; the web container uses it after format checking, while CI performs the full pinned-Python tests before release. No test runtime is required in the served web container. A build is not a deployment.

## 3 Connection and chat consent

Open WhatsApp, follow connection status and select the chats you authorize. Reception and sending are separate permissions. The separate manual sender requires exact chat/content review; provider acceptance is not delivery/read proof. Unknown results preserve the original identity and require reconciliation, never a fresh resend. Attachment download/source review exists, but real model understanding and scanned-PDF OCR are not enabled by this frontend.

## 4 Business workspace

Check summary, status, time/address and exact source revision. A conversation can contain multiple orders. Missing values stay missing. A customer proposing a change, explicitly confirming it, and the merchant approving it are different facts.

For a time or address proposal, compare the value and exact original message, then explicitly accept it. A date without a time remains tentative. If the customer has not confirmed a resolved value, accepting it saves the value as proposed: it is still waiting for the customer, rather than becoming a formal appointment. Unsupported fields, stale versions, changed sources and conflicts remain blocked.

Start, wait for customer, complete and cancel now use C's merged commands. Review the effect and version before saving. Completed/cancelled orders are final; closing deals with generated tasks and unsent business drafts, retains history and does not recall an already dispatched WhatsApp request.

A lost response preserves the original numbered command before any POST. Refresh and sign-in do not resend it. There are two explicit options: review and retry the exact original key/body/version, or use “只读核对已保存结果” to look up its immutable server receipt without executing anything. Only a matching completed receipt unlocks “结束已核对的原记录”, after a separate checkbox. Missing/unknown results retain the original record; never infer that a missing receipt means the request was not executed. Storage denial/cleanup failure blocks new writes until recovered. No password is journaled; temporary original content stays in tab session storage until verified completion.


Calendar download also checks the actual latest customer messages behind the time and any confirmed location. If a message is edited, withdrawn, missing or no longer authorized, download stops and asks you to review the source. Your stored appointment/history remains; the program does not silently cancel it.

## D-03: review a reply before approving it

Review the complete body, recipient conversation, source revisions, expiry and bound/current work-order and conversation versions. Tick explicit consent after review. **已批准，尚未发送** means only that your decision was saved. This business approval is not automatically linked to a WhatsApp send. Do not paste an old approval into a sender and assume its versions remain valid.

Reject/cancel requires a reason. Reissue creates a new pending draft, not a message. Missing-time/address and verification questions are described alongside conflict questions, including safely handled unfamiliar trigger formats. Full history retains closed records. Original-key approval recovery remains account-scoped; an unresolved legacy-entry record blocks new approvals instead of silently migrating it to a different service.

## 5 New orders and manual review

Choose an authorized conversation, enter a short summary, leave unknown time/address blank and choose the customer's latest unretracted original messages for any supplied values. Outgoing merchant messages are excluded as customer-confirmation evidence. Specific times use Hong Kong time; date-only values remain tentative. Another open order requires an explicit additional-order checkbox. Changing form/source data invalidates its review.

Saving now uses the canonical generated CreateWorkOrderCommand from merged #26. The server capability enables manual creation, order status and address confirmation in this version; a missing/failed capability response still disables dependent operations. AI creation, assignment/deferred follow-up and C-to-A sending remain unavailable.

Manual review shows safe owned/allowlisted job metadata and current original messages, not raw provider payloads. Historical rounds are labelled. Missing fields say whether customer input, clarification or merchant review is needed. Assignment/deferred-follow-up saving remains unavailable without B/C contracts. For media/partial results, use the WhatsApp attachment panel and its source review; this does not turn model output into a confirmed order.

## 6 Internal calendar and phone export

Month view starts on Monday. Choose a date; arrows move one day/week and Home/End move to the current week's ends. Today and previous/next month controls are available. All-appointments view and optional closed-order history help inspect other dates. Time is displayed in Hong Kong time; date-only entries keep their original date/timezone. Tasks are read-only because no manual completion/edit API exists.

**加入我的日历 (.ics)** downloads one current formal timed appointment after a fresh server ownership/time/source check (later address/status-only versions remain valid). Tentative, stale, unavailable and closed-order records cannot export. The file contains the business title, UTC instants, original-timezone note and a confirmed address when present. Your calendar displays the same instants in its configured timezone. Keep the downloaded business file private.

Open/import the file in your own calendar. Rescheduling does not automatically update phone/Google/Outlook calendars; reimport/update manually and check for duplicates. No Google login, subscription or two-way synchronization is implemented. Actual iPhone/Google/Outlook imports remain independent device acceptance.

## 7 Installation, logout and troubleshooting

A manifest and icon support installation/home-screen launch in compatible browsers over HTTPS or loopback. No service worker, offline business cache or background mutation is installed. Native exe/macOS bundles, signing, updates and fresh-device installation remain unimplemented. The API, worker, PostgreSQL and WAHA still need to run.

Logout clears visible account data and credentials; unresolved original journals are retained by account for recovery. If login expires, log in again. For a failed capability read, dependent actions stay disabled. For conflicts/versions, refresh and re-review. For unknown writes, reconcile the saved original operation. Never reset a business database/session to repair a frontend problem.
