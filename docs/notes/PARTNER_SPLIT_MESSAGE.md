# הודעה לפרטנר: חלוקת העבודה

> להעתיק את החלק בעברית ולשלוח. הבלוק באנגלית בסוף הוא פרומפט שהפרטנר מדביק ל-Claude Code בתחילת הסשן הראשון שלו.

---

היי, ברוך הבא ל-HarborVale.

**איפה אנחנו:** M0 סגורה (ריפו, סביבה, Flask, CI, Railway, שער 5/5). קובץ הדאטה כבר בריפו. כל מה שצריך לקרוא נמצא ב-`docs/notes/ONBOARDING_HE.html`, ואת התוכנית המלאה ב-`PLAN.md`.

**החלוקה שאני מציע:**

- **אני, מסלול A (צוות האנליסטים):** M1 הכלים של צוות 1 (טעינה, ניקוי, EDA), ואחר כך M3 צוות 1 ב-CrewAI.
- **אתה, מסלול B (החוזה וצוות מדעני הנתונים):** M2 החוזה והמאמת (`hv/contract.py`, תשע בדיקות, שש תקלות מוכנות, `scripts/break_it.py`), ואחר כך M4 הכלים של צוות 2 (פיצ'רים, שלוש וריאציות מודל, הערכה, כרטיס מודל).
- **M5 (ה-Flow) נעשה יחד**, אחרי ששני החצאים ממוזגים. אחר כך נחלק את האתר (M6, M7) ואת הסגירה (M8).

**למה זה עובד במקביל:** `PLAN.md` §3 מקבע את הממשקים מראש. §3.5 הוא החוזה (המודל של pydantic, `build_contract`, `validate`, `tamper`) ו-§3.6–3.8 הם הפיצ'רים, האימון וכרטיס המודל. M2 ו-M4 לא תלויים בסוכנים שלי, רק בפורמט של `clean_data.csv` ושל החוזה, ושניהם כתובים שם.

**נקודות תיאום, שלוש בלבד:**

1. **שינוי בחוזה = החלטה, לא תיקון.** אם תגלה ב-M2 שמשהו ב-§3.5 לא מסתדר, כותבים `D-M2-<n>` ב-`PROJECT_LOG.md` עם חלופות ומחיר ומעדכנים אותי לפני שממזגים. אני בונה על אותו פורמט.
2. **ב-M2 המשימה החמישית** (בניית החוזה האמיתי על הקובץ הנקי) מחכה למיזוג של M1 שלי. עד אז כל הבדיקות של M2 על DataFrame סינתטי, כמו ש-PLAN.md מתאר. אני אודיע כש-M1 ב-main.
3. **ב-M4 אתה צריך `clean_data.csv` וחוזה אמיתיים** כדי לרשום את המספרים ביומן. אם M4 מוכן לפני M3 שלי, זה בסדר, המספרים מגיעים מהקובץ של M1 ולא מהסוכנים.

**הפרוטוקול, בלי קיצורים:** ענף `feat/m<N>-<slug>` מ-main מעודכן, בדיקות ליד הקוד, `python scripts/gate.py --m N` ירוק, דוח `docs/reports/M<N>_HE.html`, רשומה ביומן, PR עם CI ירוק, **ואני מאשר את המיזוג שלך, אתה את שלי.** אף פעם לא push ל-main. מפתחות רק ב-`.env`.

**סנכרון:** הודעה קצרה על כל PR שנפתח (מה, תוצאת השער, מה צריך ממני). לא צריך יותר מזה.

תתחיל מסעיף 03 בדף הכניסה (הקמת סביבה), תגיד לי כשהשער של M0 עובר אצלך 5/5, ואז M2 שלך.

---

## Prompt for the partner's first Claude Code session (paste as-is)

```
I'm joining the HarborVale Workflow project as the second contributor. Read CLAUDE.md first, then the
tail of PROJECT_LOG.md, then PLAN.md §3 (contracts) and §4 (milestones). Summarise where the project is
in five lines.

My track is B: M2 (the contract and validator) and then M4 (Crew-2 tools). The other contributor owns
M1 and M3. Do not touch hv/ingest.py, hv/cleaning.py, hv/eda.py or crews/analyst/ — those are his.

Work on M2 only, on branch feat/m2-contract from an up-to-date main. Follow PLAN.md §4 M2 task by task:
hv/contract.py exactly per §3.5, tests with synthetic frames first, every validator check with a test
that makes it fail, the six tamper presets, scripts/break_it.py, and gate checks for --m 2 added to
scripts/gate.py. Task 5 (building the real contract on artifacts/crew1/clean_data.csv) waits until M1
is merged; skip it and say so.

If anything in §3.5 does not fit what you find, stop and propose a D-M2-<n> decision with alternatives
and cost; do not silently change the contract format, the other track builds on it.

Keep the per-milestone protocol from CLAUDE.md: small commits, pytest + ruff green, gate PASS, Hebrew
report in docs/reports/M2_HE.html, PROJECT_LOG entry, PR. Never push to main. Secrets only in .env.
```
