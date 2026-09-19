 START HERE — Antigravity se Assignment banane ka plan

Is kit me 4 files hain:

| File | Kaam |
|---|---|
| `START_HERE.md` | Yeh guide (kaise use karna hai) |
| `AGENTS.md` | Project root me rakho. Antigravity ke saare agents har task se pehle isse padhte hain (standing rules) |
| `docs/SPEC.md` | Poora technical design (schema, API, pipeline, confidence formula). Agent iska reference lega |
| `PHASE_PROMPTS.md` | Phase 0 se 10 tak ke copy-paste prompts + style footer. Ek-ek karke Antigravity me daalo |

Idea simple hai: **ek bada prompt mat do**. Bade prompt me agent context kho deta hai aur half-baked code deta hai. Isliye rules + spec repo me rakho, aur kaam phase-by-phase karwao.

---

## 1. Setup (15–20 min)

1. Machine par install hona chahiye: **Docker Desktop**, **Git**, Python 3.12 (optional, agar local run karna ho).
2. Naya folder banao, jaise `doc-intelligence-service`, aur `git init` chala do.
3. Is kit ki files copy karo:
   - `AGENTS.md` → project root
   - `docs/SPEC.md` → `docs/SPEC.md`
   - `PHASE_PROMPTS.md` → `docs/PHASE_PROMPTS.md` (optional, sirf reference)
4. Antigravity me **File → Open Folder** se *isi project folder* ko open karo (parent folder nahi).
5. Gemini API key chahiye (Google AI Studio se free tier mil jaata hai). Ise sirf `.env` me rakhna, kabhi commit mat karna. Agar key nahi hai to system `EXTRACTOR=rules` mode me bhi chalna chahiye (spec me hai), lekin quality kam hogi.
6. Assignment PDF ko `docs/assignment.pdf` me rakh do taaki agent zaroorat par dekh sake.

> Note: Antigravity ke rules/workflows ka folder naam version ke hisaab se `.agent/` ya `.agents/` ho sakta hai. Isliye maine `AGENTS.md` (project root) use kiya hai, jo aam taur par padha jaata hai. Agar aapke version me alag rules panel hai, to wahan bhi `AGENTS.md` ka content paste kar sakte ho.

## 2. Antigravity settings

- **Mode:** Phase 0, 3, 4, 5 me **Planning** mode. Chhote fixes ya doc edits me **Fast**.
- **Model:** Jo sabse strong model quota me available ho (Gemini Pro-class ya Claude Sonnet/Opus-class, jo bhi aapke dropdown me dikhe). Phase 0, 4, 5 sabse important hain, unme best model lagao.
- **Terminal policy:** "Review-driven" rakho. Agent commands chalayega, lekin `rm -rf`, `docker system prune`, `git push --force` jaise commands ko khud approve karo.
- **Har phase = nayi conversation.** Purani conversation lambi ho jaaye to agent bhatakne lagta hai. Har phase ke end me agent `docs/PROGRESS.md` update karta hai, isliye nayi conversation me bhi context nahi jaata.
- **Har phase ke baad `git commit`.** Kuch toot jaaye to rollback aasan hoga.
- Phase 0 me agent jo **Implementation Plan** artifact banaye, use approve karne se pehle padho aur comments do.

## 3. 24 ghante ka realistic plan

| Phase | Kaam | Time |
|---|---|---|
| 0 | Plan + ambiguities | 0.5 h |
| 1 | Scaffold, Docker, DB schema, Auth | 2 h |
| 2 | Upload, security, storage, status APIs | 2 h |
| 3 | Ingest + OCR + rules parser (end-to-end slice, bina LLM ke) | 3 h |
| 4 | LLM extraction, grounding, page stitching, figures | 4 h |
| 5 | Answer key + multi-document links | 2.5 h |
| 6 | Confidence, warnings, review APIs, OpenAPI polish | 2 h |
| 7 | Sample docs generator, tests, evaluation | 3 h |
| 8 | Docs, Postman, demo runner, evidence | 3 h |
| 9 | Polish pass (human-style cleanup) | 1 h |
| 10 | Final audit (fresh clone test) | 1.5 h |

Total ~24.5 h, jo bahut tight hai. Style rules Phase 1 se hi lagte hain, isliye Phase 9 asal me 45 minute ka quick sweep hona chahiye. Isliye **Phase 3 ke baad hi ek chalta hua end-to-end slice** aa jaana chahiye. Waqt kam pade to yeh cut karo (SPEC me "Cut list" bhi hai):

1. MinIO/S3 (local volume storage kaafi hai)
2. Hindi OCR, passage-based questions
3. Reprocess endpoint, link-suggestions, CI workflow
4. Advanced table extraction (sirf markdown + crop image rakho)

**Kabhi cut mat karo:** authz checks, file validation, async processing, answer-key "not_found/ambiguous" handling, confidence flags, real demo evidence, tests.

## 4. Zaroori baatein (assignment ki shart)

1. **Code samajhna zaroori hai.** Assignment kehta hai ki aap system explain kar sakein. Agle round me shayad interview hoga. Har phase ke baad agent se poochho: *"Explain the design of what you just built, file by file, and the top 3 trade-offs."* Aur khud ek baar code padho.
2. **Evidence fabricate mat karna.** Demo outputs, screenshots aur test results asli run se aane chahiye. Phase 8 ka prompt is par strict hai. Agent agar "expected output" likh de, use reject karo.
3. **AI disclosure:** `docs/AI_DISCLOSURE.md` me likho ki development me Antigravity (aur jo model use hua) aur runtime par Gemini API/Tesseract use hue.
4. **Secrets:** `.env` gitignore me ho, `.env.example` me sirf placeholders. Submit karne se pehle `git log -p | grep -i "api_key"` jaisa check chalao (Phase 9 me hai).
5. Synthetic sample documents use karo (script se generate honge). Real exam papers copyrighted ho sakte hain. Chaho to 1–2 publicly available past papers khud add kar sakte ho.

## 5. Human-style quality (AI-generated jaisa na lage)

Kit me ab style rules bhi hain: `AGENTS.md` ka "Authorship and style" section, `SPEC.md` §22, aur Phase 9 ka polish pass. Har prompt ke end me "Style footer" bhi paste karna (`PHASE_PROMPTS.md` ke top me hai). Isse code, comments, log messages, README aur commit messages natural aur properly finished aayenge.

Lekin asli farak tumhare khud ke haath lagane se padta hai:

1. **Har file khud padho.** Jo samajh na aaye use agent se samjhwao ya simple karwao. Jo code tum explain nahi kar sakte, use submit mat karo.
2. **Apna touch do.** Kuch variable/function naam apne style me rename karo, aur ek-do chhote hisse khud likho (jaise koi parser ya test). Isse code me tumhari awaaz aati hai.
3. **README intro aur DECISIONS.md ke reasons apne shabdon me likho.** Agent ka draft base ban sakta hai, final voice tumhari honi chahiye.
4. **Commits chhote aur natural rakho** (`fix option parser for (i)-(iv)`). Ek giant commit mat karo, aur history ya dates ke saath chhedchhad mat karo.
5. **Kahaniyan mat gadho.** Jo problem, benchmark ya "maine yeh try kiya tha" hua hi nahi, use docs me mat likho. Limitations sirf woh likho jo sach me mile (`PROGRESS.md` isi ke liye hai).
6. **Disclosure sachchi rakho.** Assignment AI use allow karta hai par disclose karne ko kehta hai, isliye `AI_DISCLOSURE.md` poora aur accurate rahe. "Human-like" ka matlab hai saaf, natural aur samjha hua kaam, AI use chhupana nahi.

Kuch aam "AI wale nishaan" jo submit karne se pehle hata do: emojis, "robust / seamless / comprehensive" jaise filler words, har line par comment, har function par docstring, har section me ek hi jaisi 3 bullets, `utils.py` / `helpers.py` jaise generic naam, adhoore stubs aur unused code.

## 6. Agar agent bhatak jaye

Yeh "reset prompt" paste karo:

```
Stop. Re-read AGENTS.md, docs/SPEC.md and docs/PROGRESS.md.
Summarize in 10 lines: what is done, what is failing, what you were about to do.
Then fix only the currently failing tests/commands. Do not refactor unrelated code.
```

## 7. Interview ke liye taiyari (tumhe bolna aana chahiye)

- Digital vs scanned page ka decision kaise hota hai?
- LLM hallucinate kare to kaise pakadte ho? (grounding score + independent OCR confidence)
- Cross-page question kaise stitch hota hai, aur stitch galat ho to?
- Answer key ambiguous ho (duplicate numbering across sections) to kya hota hai?
- Confidence formula kya hai aur thresholds kyun aise rakhe?
- 100 documents ek saath aaye to bottleneck kahan aayega? (LLM rate limit, OCR CPU, DB)
- Auth: doc ka owner check kaise enforce hota hai? Foreign doc par 404 kyun, 403 kyun nahi?
