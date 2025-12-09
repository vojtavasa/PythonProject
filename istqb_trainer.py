import json
import time
import random
from pathlib import Path

import streamlit as st

# Mapování jazyk -> soubor s otázkami
LANG_FILES = {
    "Čeština": "questions_cs.json",
    "English": "questions_en.json",
}

STATS_FILE = "stats.json"


@st.cache_data
def load_questions(file_name: str):
    path = Path(file_name)
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    sets = {}
    for q in data:
        s = q["set"]
        sets.setdefault(s, []).append(q)

    for s in sets:
        sets[s] = sorted(sets[s], key=lambda x: x.get("id", 0))

    return sets


def load_stats() -> dict:
    path = Path(STATS_FILE)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_stats(stats: dict) -> None:
    path = Path(STATS_FILE)
    with path.open("w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def update_stats_for_run(questions):
    """Aktualizuje stats.json pro právě dokončený test."""
    username = st.session_state.username
    language = st.session_state.language

    stats = load_stats()
    user_stats = stats.setdefault(username, {"questions": {}})
    q_stats = user_stats["questions"]

    for q in questions:
        key = f"{language}:{q['set']}:{q['id']}"
        rec = q_stats.setdefault(key, {"seen": 0, "correct": 0})
        rec["seen"] += 1

        qid = (q["set"], q["id"], language)
        user_answer_index = st.session_state.answers.get(qid, None)
        if user_answer_index == q["correct_index"]:
            rec["correct"] += 1

    save_stats(stats)


def get_questions_for_mode(sets, selected_set, practice_mode):
    """Vrátí seznam otázek podle zvoleného režimu tréninku."""
    language = st.session_state.language
    username = st.session_state.username

    questions = sets[selected_set]

    if practice_mode == "Targeted (slabé otázky)":
        stats = load_stats()
        user_stats = stats.get(username, {}).get("questions", {})

        weak_questions = []
        for q in questions:
            key = f"{language}:{q['set']}:{q['id']}"
            rec = user_stats.get(key)
            if not rec:
                continue
            seen = rec.get("seen", 0)
            correct = rec.get("correct", 0)
            if seen == 0:
                continue
            success_rate = correct / seen
            if success_rate < 0.7:
                weak_questions.append(q)

        if weak_questions:
            st.info(f"Targeted mode: nalezeno {len(weak_questions)} slabších otázek v sadě {selected_set}.")
            return weak_questions
        else:
            st.info(
                "Nemáš v této sadě žádné výrazně slabé otázky "
                "(nebo jsi je ještě nikdy neměl). Používám standardní režim."
            )
            return questions

    return questions


def init_state(selected_set, language, shuffle_questions, shuffle_options, username, practice_mode):
    st.session_state.language = language
    st.session_state.selected_set = selected_set
    st.session_state.shuffle_questions = shuffle_questions
    st.session_state.shuffle_options = shuffle_options
    st.session_state.username = username
    st.session_state.practice_mode = practice_mode

    st.session_state.started = False
    st.session_state.finished = False

    st.session_state.current_index = 0
    st.session_state.question_order = []
    st.session_state.option_orders = {}
    st.session_state.answers = {}
    st.session_state.start_time = None
    st.session_state.stats_updated = False


def ensure_order_structures(questions):
    total = len(questions)
    if not st.session_state.question_order or len(st.session_state.question_order) != total:
        order = list(range(total))
        if st.session_state.shuffle_questions:
            random.shuffle(order)
        st.session_state.question_order = order

    for q in questions:
        qid = (q["set"], q["id"], st.session_state.language)
        if qid not in st.session_state.option_orders:
            opt_order = list(range(len(q["options"])))
            if st.session_state.shuffle_options:
                random.shuffle(opt_order)
            st.session_state.option_orders[qid] = opt_order


def show_user_stats(username: str):
    """Vykreslí statistiky pro daného uživatele v UI."""
    st.header(f"Statistiky uživatele: {username}")

    stats = load_stats()
    user = stats.get(username)
    if not user or "questions" not in user or not user["questions"]:
        st.info("Zatím nemáš nasbírané žádné statistiky. Zkus si udělat pár testů 🙂")
        return

    q_stats = user["questions"]

    # Přehled celkem
    total_seen = 0
    total_correct = 0
    by_lang_set = {}  # (lang, set) -> {seen, correct}

    for key, rec in q_stats.items():
        # key: "Čeština:A:1" nebo "English:B:5"
        try:
            lang, s, qid = key.split(":")
        except ValueError:
            continue

        seen = rec.get("seen", 0)
        correct = rec.get("correct", 0)

        total_seen += seen
        total_correct += correct

        grp = by_lang_set.setdefault((lang, s), {"seen": 0, "correct": 0})
        grp["seen"] += seen
        grp["correct"] += correct

    if total_seen == 0:
        st.info("Máš statistiky, ale všude 'seen = 0'. Něco je špatně – dej vědět :)")
        return

    overall_rate = total_correct / total_seen * 100
    st.subheader("Celkový přehled")
    st.write(f"- Celkem odpovědí: **{total_seen}**")
    st.write(f"- Správných odpovědí: **{total_correct}**")
    st.write(f"- Celková úspěšnost: **{overall_rate:.1f} %**")

    # Tabulka podle jazyk + sada
    st.subheader("Podle jazyka a sady")
    rows = []
    for (lang, s), rec in sorted(by_lang_set.items()):
        seen = rec["seen"]
        correct = rec["correct"]
        rate = correct / seen * 100 if seen > 0 else 0.0
        rows.append(
            {
                "Jazyk": lang,
                "Sada": s,
                "Odpovědí celkem": seen,
                "Správně": correct,
                "Úspěšnost %": round(rate, 1),
            }
        )
    st.table(rows)

    # Nejslabší otázky
    st.subheader("Nejslabší otázky")
    weak = []
    for key, rec in q_stats.items():
        seen = rec.get("seen", 0)
        correct = rec.get("correct", 0)
        if seen == 0:
            continue
        rate = correct / seen
        if rate < 0.7:  # slabé (<70 %)
            lang, s, qid = key.split(":")
            weak.append(
                {
                    "Jazyk": lang,
                    "Sada": s,
                    "ID otázky": int(qid),
                    "Odpovědí": seen,
                    "Správně": correct,
                    "Úspěšnost %": round(rate * 100, 1),
                }
            )

    if not weak:
        st.info("Nemáš žádné výrazně slabé otázky (pod 70 % úspěšnosti). Nice! 🎉")
    else:
        weak_sorted = sorted(weak, key=lambda x: x["Úspěšnost %"])
        st.table(weak_sorted[:20])


def main():
    st.title("ISTQB Trainer")

    # ---- USER / LOGIN ----
    username = st.sidebar.text_input(
        "User / přezdívka",
        value="",
        placeholder="Vaše přezdívka"
    )

    if not username.strip():
        st.warning("Zadej prosím jméno / přezdívku v levém panelu.")
        st.stop()

    app_mode = st.sidebar.radio("Mód", ["Trénink", "Statistiky"])

    if app_mode == "Statistiky":
        show_user_stats(username)
        return

    # ---- JAZYK A SADA (TRÉNINK) ----
    language = st.sidebar.selectbox("Jazyk / Language", list(LANG_FILES.keys()))
    questions_file = LANG_FILES[language]

    sets = load_questions(questions_file)
    if not sets:
        st.error(f"Soubor s otázkami '{questions_file}' nebyl nalezen nebo je prázdný.")
        st.stop()

    set_names = sorted(sets.keys())
    selected_set = st.sidebar.selectbox("Vyber sadu otázek", set_names)

    practice_mode = st.sidebar.selectbox(
        "Režim tréninku",
        ["Standard (všechny otázky)", "Targeted (slabé otázky)"],
    )

    shuffle_questions = st.sidebar.checkbox("Náhodné pořadí otázek", value=True)
    shuffle_options = st.sidebar.checkbox("Náhodné pořadí odpovědí", value=True)

    # ---- RESET STAVU PŘI ZMĚNĚ NASTAVENÍ ----
    if (
        "selected_set" not in st.session_state
        or st.session_state.selected_set != selected_set
        or st.session_state.language != language
        or st.session_state.shuffle_questions != shuffle_questions
        or st.session_state.shuffle_options != shuffle_options
        or st.session_state.username != username
        or st.session_state.practice_mode != practice_mode
    ):
        init_state(selected_set, language, shuffle_questions, shuffle_options, username, practice_mode)

    questions = get_questions_for_mode(sets, selected_set, practice_mode)
    total_questions = len(questions)

    if total_questions == 0:
        st.warning("V tomto režimu nejsou žádné otázky k zobrazení.")
        st.stop()

    # ---- ÚVOD PŘED STARTEM ----
    if not st.session_state.started and not st.session_state.finished:
        st.write(
            f"Uživatel: **{username}**  \n"
            f"Jazyk: **{language}**, sada: **{selected_set}**  \n"
            f"Režim: **{practice_mode}**  \n"
            f"Počet otázek: **{total_questions}**"
        )
        if st.button("Začít test"):
            st.session_state.started = True
            st.session_state.start_time = time.time()
            ensure_order_structures(questions)
            st.rerun()
        return

    # ---- ZOBRAZENÍ VÝSLEDKŮ ----
    if st.session_state.finished:
        show_results(questions)
        if st.button("Zkusit znovu tuto kombinaci"):
            init_state(
                selected_set,
                language,
                st.session_state.shuffle_questions,
                st.session_state.shuffle_options,
                username,
                practice_mode,
            )
            st.rerun()
        return

    # ---- PROBÍHAJÍCÍ TEST ----
    ensure_order_structures(questions)

    order = st.session_state.question_order
    pos = st.session_state.current_index
    q_index = order[pos]
    question = questions[q_index]

    qid = (question["set"], question["id"], st.session_state.language)

    st.markdown(
        f"**Otázka {pos + 1}/{total_questions} "
        f"(ID {question['set']}-{question['id']})**"
    )
    st.write(question["question"])

    if st.session_state.start_time is not None:
        elapsed = int(time.time() - st.session_state.start_time)
        st.info(f"Čas: {elapsed // 60:02d}:{elapsed % 60:02d}")

    opt_order = st.session_state.option_orders[qid]
    shuffled_options = [question["options"][i] for i in opt_order]

    prev_original_index = st.session_state.answers.get(qid, None)
    if prev_original_index is not None:
        try:
            prev_shuffled_index = opt_order.index(prev_original_index)
        except ValueError:
            prev_shuffled_index = 0
    else:
        prev_shuffled_index = 0

    selected_option = st.radio(
        "Vyber odpověď:",
        shuffled_options,
        index=prev_shuffled_index,
        key=f"q_{qid}",
    )

    selected_shuffled_index = shuffled_options.index(selected_option)
    original_index = opt_order[selected_shuffled_index]
    st.session_state.answers[qid] = original_index

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Předchozí", disabled=(pos == 0)):
            st.session_state.current_index -= 1
            st.rerun()

    with col2:
        if st.button("Další", disabled=(pos == total_questions - 1)):
            st.session_state.current_index += 1
            st.rerun()

    with col3:
        can_finish = len(st.session_state.answers) >= total_questions
        if st.button("Vyhodnotit", disabled=not can_finish):
            st.session_state.finished = True
            st.rerun()


def show_results(questions):
    st.subheader("Výsledky")

    correct = 0
    total = len(questions)

    if not st.session_state.stats_updated:
        update_stats_for_run(questions)
        st.session_state.stats_updated = True

    for q in questions:
        qid = (q["set"], q["id"], st.session_state.language)
        user_answer_index = st.session_state.answers.get(qid, None)
        correct_index = q["correct_index"]

        if user_answer_index == correct_index:
            correct += 1
            st.success(f"Otázka {q['set']}-{q['id']}: Správně")
        else:
            st.error(f"Otázka {q['set']}-{q['id']}: Špatně")

        st.write(f"Správná odpověď: {q['options'][correct_index]}")
        st.markdown("---")

    score_percent = round(correct / total * 100, 1)
    st.success(f"Výsledek: {correct}/{total} ({score_percent} %)")

    if st.session_state.start_time is not None:
        elapsed = int(time.time() - st.session_state.start_time)
        st.info(f"Čas pokusu: {elapsed // 60:02d}:{elapsed % 60:02d}")


if __name__ == "__main__":
    main()
