import json
import re
from pathlib import Path

import pdfplumber

# ↓↓↓ TADY UPRAV NÁZVY SOUBORŮ PODLE TVÝCH EN PDF ↓↓↓
SETS = [
    ("A", "ISTQB_CTFL_v4.0_Sample-Exam-A-Questions_v1.7.pdf", "ISTQB_CTFL_v4.0_Sample-Exam-A-Answers_v1.7.pdf"),
    ("B", "ISTQB_CTFL_v4.0_Sample-Exam-B-Questions_v1.7.pdf", "ISTQB_CTFL_v4.0_Sample-Exam-B-Answers_v1.7.pdf"),
    ("C", "ISTQB_CTFL_v4.0_Sample-Exam-C-Questions_v1.6.pdf", "ISTQB_CTFL_v4.0_Sample-Exam-C-Answers_v1.6.pdf"),
    ("D", "ISTQB_CTFL_v4.0_Sample-Exam-D-Questions_v1.5.pdf", "ISTQB_CTFL_v4.0_Sample-Exam-D-Answers_v1.5.pdf"),
]

# ====== REGEXE PRO ANGLICKOU VERZI ======
# Např. "Question 1 (1 point)" nebo "Question 1 (1 mark)"
QUESTION_HEADER_RE = re.compile(
    r"Question\s+#?(\d+)\s*\(1\s+(?:Point|Mark)\)",
    re.IGNORECASE
)
# Řádky typu "a) some text"
ANSWER_LINE_RE = re.compile(r"^([abcd])\)\s*(.+)")
# Řádky v answer key: "1 a" / "1 a)" apod.
KEY_ROW_RE = re.compile(r"^(\d+)\s+([abcd])\b", re.IGNORECASE)


def extract_text(pdf_path: Path) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        texts = []
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                texts.append(t)
        return "\n".join(texts)


def parse_questions(text: str):
    """
    Vrátí dict: { číslo_otázky: { 'question': text, 'options': [a,b,c,d] } }
    """
    result = {}
    parts = QUESTION_HEADER_RE.split(text)

    for i in range(1, len(parts), 2):
        q_number = int(parts[i])
        block = parts[i + 1]

        lines = [l.strip() for l in block.splitlines() if l.strip()]
        question_lines = []
        option_map = {}

        mode = "question"
        for line in lines:
            m = ANSWER_LINE_RE.match(line)
            if m:
                mode = "answers"
                letter, txt = m.groups()
                option_map[letter.lower()] = txt.strip()
            else:
                if mode == "question":
                    question_lines.append(line)
                else:
                    # pokračování textu předchozí odpovědi (zalomené řádky)
                    if option_map:
                        last_key = sorted(option_map.keys())[-1]
                        option_map[last_key] += " " + line.strip()

        if len(option_map) < 4:
            print(f"Varování: otázka {q_number} nemá 4 odpovědi, našel jsem: {list(option_map.keys())}")

        question_text = " ".join(question_lines).strip()
        options = [option_map.get(ch, "") for ch in "abcd"]

        result[q_number] = {
            "question": question_text,
            "options": options,
        }

    return result


def parse_answer_key(text: str):
    """
    Vrátí dict: { číslo_otázky: 'a'/'b'/'c'/'d' }
    Z textu hledá část s 'Answer key'.
    """
    idx = text.lower().find("answer key")
    if idx != -1:
        text = text[idx:]

    key = {}
    for line in text.splitlines():
        line = line.strip()
        m = KEY_ROW_RE.match(line)
        if m:
            q_num = int(m.group(1))
            letter = m.group(2).lower()
            key[q_num] = letter
    return key


def main():
    all_questions = []

    for set_id, q_pdf, a_pdf in SETS:
        q_path = Path(q_pdf)
        a_path = Path(a_pdf)

        print(f"Zpracovávám EN sadu {set_id}...")

        q_text = extract_text(q_path)
        # DEBUG: uložíme text do souboru na prozkoumání
        debug_path = Path(f"debug_{set_id}_questions.txt")
        debug_path.write_text(q_text, encoding="utf-8")
        print(f"  Debug text uložen do {debug_path}")

        a_text = extract_text(a_path)

        questions = parse_questions(q_text)
        print(f"  Načteno {len(questions)} otázek v sadě {set_id}")
        answer_key = parse_answer_key(a_text)

        for q_num, q_data in questions.items():
            if q_num not in answer_key:
                print(f"  ⚠️  Nemám správnou odpověď pro otázku {q_num} v sadě {set_id}")
                continue

            letter = answer_key[q_num]
            correct_index = "abcd".index(letter)

            all_questions.append(
                {
                    "set": set_id,
                    "id": q_num,
                    "language": "en",
                    "question": q_data["question"],
                    "options": q_data["options"],
                    "correct_index": correct_index,
                }
            )

    out_path = Path("questions_en.json")
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(all_questions, f, ensure_ascii=False, indent=2)

    print(f"Hotovo, uloženo do {out_path.resolve()}")


if __name__ == "__main__":
    main()
