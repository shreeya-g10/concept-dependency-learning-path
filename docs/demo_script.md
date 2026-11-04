# Demo script: AVL Trees (demo), about 6 minutes

What the demo shows: upload → topic map → AI checks and review → quick check → study plan. It uses one course, already built, and shows it on the website with **no AI running**.

The course is `outputs/avl_demo_discover_v4/`. On the website it is called **AVL Trees (demo)**.

## Say this first

> This course was built earlier on a free GPU, so we are not building anything live. That run took about 34 minutes, after about 4 minutes of reading the deck in an earlier run, and it reused saved replies for 126 of its 654 AI calls.
>
> It is a demo deck we wrote ourselves. Many slides say outright what comes first, so this is easier than a real textbook.
>
> The numbers on screen describe this deck. They are not research results. Our main experiment, RQ1, on whether the checking agent improves precision, is still pending.

The times come from `colab_calls.summary.json` in the course folder and the same file from the first run: discover 632 s, validate 677 s, quiz 714 s, path 3 s, which is 2,026 s. The first run's reading step took 226 s.

## Before you present (5 minutes)

1. Get the course: `outputs/avl_demo_discover_v4/` must be in the repo folder. Keep a copy:
   ```bash
   mkdir -p ~/Desktop/demo_backup && cp -R outputs/avl_demo_discover_v4 ~/Desktop/demo_backup/
   ```
2. Stop Ollama, so the demo shows that the website does not need it: click the Ollama icon in the menu bar, then **Quit Ollama**. If it stays running, use `pkill -TERM -x Ollama; pkill -TERM -x ollama`. Check with `curl -s -m 2 http://localhost:11434`, which should print nothing. Check again just before you start, because it can come back by itself.
3. Start the website, then open each page once, so nothing loads for the first time on stage:
   ```bash
   .venv/bin/streamlit run website/Home.py
   ```
4. On **Home**, pick **AVL Trees (demo)**. Another subject may be selected at first.
5. **After every rehearsal,** quick check answers are saved in the course folder, so move them out. Keep demo answers away from real ones:
   ```bash
   mv outputs/avl_demo_discover_v4/student_answers.json ~/Desktop/demo_backup/rehearsal_answers.json
   ```

## The demo

| Time | Page and clicks | Say |
|---|---|---|
| 0:00 | **Home.** Show **Pick your subject**: **AVL Trees (demo)**. | Say the opening text above. The problem: "I want to learn this topic. What should I study first, given what I already know?" |
| 0:40 | **1 Add your notes.** Show it, and **do not run it**. | "A teacher or student uploads notes here. A real build takes a GPU and about half an hour, so this course was built earlier." The warning that the AI helper is off is correct, because Ollama is off. **Don't tap Try the sample course:** it changes the subject. |
| 1:10 | **Topic map.** **All Topics** is the only view so far. Tap **See full map**. | "Every arrow is a link the checks accepted: 33 of them, across 25 of the 26 topics. Solid means you need it first. Dashed means it helps." |
| 1:50 | **AI checks and review** (under **For teachers**). Show the counts, then find **Binary Tree → Binary Search Tree**. | "A second model checks each link, against quotes from the deck. 33 accepted, 43 rejected, 59 need a person." Use the wording under **What the counts mean**. "Discovery proposed this link in both directions, so the system won't choose. A teacher decides." Don't click, unless you decided to beforehand. |
| 3:00 | **3 Quick check: the correct path.** Tap **Binary Search**, and answer as in the table below. | "It only asks the topics this one depends on. 'Have you studied it?' only picks the first question. It never marks a topic as known. A right answer moves up a level, and only a real hard question earns Know it." |
| 3:40 | The plan opens by itself: "Your answers suggest you already know what you need for Binary Search." | "This student has nothing to study." |
| 3:50 | **Reload the browser page.** Open **Home**, and pick **AVL Trees (demo)** again. | "A new student." The reload is needed: answers last for the browser session, so the same topic would go straight back to the plan. |
| 4:00 | **3 Quick check: the wrong path.** Tap **Binary Search**, and answer as in the table below. | "A wrong easy answer means start from the basics. Binary Search needs Array, so it isn't asked. Time Complexity doesn't need Array, so it still is." |
| 4:50 | **4 My study plan** opens by itself: **Study this next: Array**, with the page to read. | "Same course, different plan. Array: start from the basics. Time Complexity: quick revision. Binary Search: not checked yet, because it needs Array first." |
| 5:20 | **Topic map.** Choose **My Study Path**. | "The same plan as a picture: their next step, what needs revision, and their goal." |
| 5:45 | Stop here. | Recap: built once on a free GPU, checked by a second model, reviewed by a person, and a different plan for each student. |

**About the Topic map:** **My Study Path** only appears once a student has a plan, so show **All Topics** first and come back after the quick check.

### What to tap

Answers are shuffled, but in the same order every time, so find them by their words.

**Correct path:**

| Screen | Tap |
|---|---|
| Have you studied Array? | Yes |
| How do you access an element in an array by its index? | It takes O(1) time |
| How does binary search work in a sorted array? | It checks the middle element and repeats on the half containing the key |
| Have you studied Time Complexity? | Yes |
| What is Big-O notation used for in the context of Time Complexity? | To compare algorithms without running them |
| What is the Time Complexity of Binary Search? | O(log n) |
| Have you studied Binary Search? | Yes |
| What is the time complexity of Binary Search? | O(log n) |
| Why does Binary Search take O(log n) time? | Because it halves the search range with each comparison |

**Wrong path:**

| Screen | Tap |
|---|---|
| Have you studied Array? | Not sure |
| How do you access an element in an array by its index? | It takes O(n) time (wrong, on purpose) |
| The kind message | Keep going |
| Have you studied Time Complexity? | Yes |
| What is Big-O notation used for in the context of Time Complexity? | To compare algorithms without running them |
| What is the Time Complexity of Binary Search? | O(n) (wrong, on purpose) |
| The kind message | Keep going |

## What the counts mean

Say these plainly if asked:

- **Rejected does not mean wrong here.** All 43 rejected links were rejected as redundant, meaning another route between the topics seemed to exist. None was rejected on its evidence or meaning. Don't say the AI caught 43 bad links.
- **Most review links are about direction.** 54 of the 59 are there because discovery proposed both directions.
- **The questions are AI-written, and no teacher has approved them.** The difficulty labels are the AI's suggestions. Of the questions drafted, 68% to 77% per level failed the checks and were dropped, which left 35.
- **Some kept questions are still poor.** On a read-through, 20 of the 35 look good, 11 doubtful and 4 wrong. The demo path has no wrong ones, but three of its questions are rough, such as the first one, which asks "how" but offers times.

## Stay on the Binary Search path

It was chosen because all three topics have a real hard question and none of its questions looks wrong. Avoid these on stage:

| Avoid | Why |
|---|---|
| **AVL Tree** as the target | The name suits the deck, but AVL Tree has no hard question, so it can never reach Know it. Its current path also skips Binary Search Tree and Rotation, because those links are not accepted. |
| **Rotation** questions | The one Rotation question changes the deck's example from 30, 10, 20 to 10, 30, 20, so its marked answer is wrong. |
| **Balance Factor**, **Leaf**, **Queue** | Each has a wrong question. |

**If you decide review links first:** accepting Binary Tree → Binary Search Tree, Rotation → AVL Tree or Balance Factor → Rotation does not change the Binary Search path. Accepting a review link into Array, Time Complexity or Binary Search can, so run through the path again if you do.

## Backup plan

| If this happens | Do this |
|---|---|
| A page shows an error or odd data | Stop the website (Ctrl+C), start it again, and reload. Still broken: move `outputs/avl_demo_discover_v4` aside, copy it back from `~/Desktop/demo_backup/`, and reload. |
| The subject is not listed | The folder must be `outputs/avl_demo_discover_v4/`, with `concepts.json` and `validated_graph.json` in it. |
| Another subject's data is showing | Open **Home** and pick **AVL Trees (demo)**. |
| Quick check goes straight to the plan | Answers from earlier in this browser session are still there. Reload the page, then pick the subject again on **Home**. |
| A question is not in the tables above | Say the path can vary, answer one right and one wrong, and open **4 My study plan**. |
| Someone asks to upload something live | Say a real build takes about half an hour on a GPU, and offer to show it afterwards. |
| The website will not start | Show screenshots of each page. Take them while rehearsing. |
