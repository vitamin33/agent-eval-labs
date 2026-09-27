# Next experiment: exp3, deterministic checkpoints at hand-off points

> The prompt for the next research session, in Ukrainian as it will be given.
> Written 2026-09-27 after the September series shipped. Update it when the
> direction changes; delete it when exp3 starts and RESEARCH.md exists.

Контекст: репо agent-eval-labs (github.com/vitamin33/agent-eval-labs), гілка
replicate-experiment-1 (влити в main перед стартом). Два експерименти завершені
й опубліковані: exp1 verifier-gap (single answer: 0/50 false greens, H1–H4
сфальсифіковані, реплікація у вересні на перейменованій моделі), exp2
agent-verifier-gap (trajectory: false-green rate 45/45 = 100%, detection 8/70,
median contamination depth 8 кроків, per-step "double-check" prompt дав +5.7 pp
при 1.03x, тобто нічого). Блог-серія з трьох постів готова до публікації на
serbyn.io (гілка blog/agent-says-done у serbyn-pro). Усі числа в README
перевіряються тестами проти сирих JSONL. Гейти G0–G8 зелені. Скіли
/audience-clarity і /voice доступні глобально (~/.claude/skills), голос
компілюється з ascend: `make voice && make skill-sync`.

Мета наступного експерименту (exp3): перетворити знахідку exp2 на перевірену
рецептуру. Ми знаємо, що агент не помічає зіпсований крок і що prompt
"перевіряй себе" не допомагає. Не знаємо, ЩО допомагає і скільки це коштує.
Питання: чи детермінована звірка на межах кроків (checkpoint), а не в кінці,
знижує trajectory false-green rate, і за яку ціну. Це прямо те, що флагманський
пост радить командам "у понеділок", і зараз ця порада не виміряна.

Цінність за трьома лініями:
- бізнес: прескрипція з ціною ("checkpoint кожні N кроків коштує +X%, прибирає
  Y% false greens"), яку CTO може поставити в бюджет;
- інженерія: чи checkpoint має бути примусовим у harness, чи достатньо дати
  агенту інструмент і він сам ним користуватиметься (гіпотеза: не буде);
- дослідження: чи є "детектор" проблемою моделі чи проблемою доступу до
  джерела істини. Якщо примусова звірка працює, а добровільна ні, то gap
  у волі, а не в здатності.

Дизайн (пре-реєстрація перед даними, як у RESEARCH.md exp2):
- Та сама orderdesk-середа й ті самі 4 ін'єкції. Три режими:
  (a) inject — baseline з exp2, для порівняння в одному прогоні;
  (b) inject_tool — агент отримує додатковий інструмент `reconcile(entity)`,
      що перераховує стан із джерела; використання добровільне;
  (c) inject_enforced — harness після кожного tool-виклику, що змінює стан,
      сам викликає reconcile і підкладає результат агенту як tool result.
- Метрики: trajectory false-green rate, detection rate, contamination depth,
  reconcile usage rate у (b), cost multiplier (b)/(a) і (c)/(a).
- Гіпотези з порогами (запропонуй у RESEARCH.md, зафіксуй тестом):
  H1 (c) знижує false-green rate нижче 30% (з 100%);
  H2 (b) usage rate reconcile < 50% (агент не користується добровільно);
  H3 (b) false-green rate не відрізняється від (a) на 95% інтервалі;
  H4 (c) cost multiplier < 1.5x;
  H5 contamination depth у (c) медіана <= 2.
- Stopping rule staged, як у exp2: stage 1 k=2, 99% інтервал; stage 2 k=5.
- Бюджет: exp2 коштував $1.69 за 280 траєкторій; тут 3 режими × 8 задач ×
  4 ін'єкції × k — оціни в PLAN.md до запуску, стеля $5.

Обов'язкові передумови (Фаза 0):
1. Виправити injection, що не спрацьовує в 43.8% спроб (див.
   agent-verifier-gap/CALIBRATION.md). Це не має повторитися: перед stage 1
   гейт G7 має підтверджувати, що кожна пара task×injection спрацьовує.
2. Модель: config пінить deepseek-v4-flash, API зараз віддає deepseek-flash.
   Рішення свідоме: перепінити на deepseek-flash і зафіксувати в RESEARCH.md
   Amendment, що exp3 на іншому id, ніж exp2; не порівнювати exp3 (a) з exp2
   як "той самий baseline", лише всередині одного прогону.
3. Записи schema v2 (per-call cost, cache miss/write, served model), pin check
   у гейті, як у exp1.

Фази як раніше: 1 аудит без змін у коді, показати план, чекати підтвердження;
2 мінімальна доробка; 3 прогін + верифікація + вартість, сирі JSONL, жодних
округлень; 4 README для не-інженерів зверху й інженерів знизу, прогнати через
/voice check і /audience-clarity, гейт: відтворюється з нуля і цифри збігаються
з даними.

Після exp3 наступний кандидат, якщо буде бюджет: крос-модельна реплікація
exp2 на 2–3 моделях (Claude Haiku 4.5, один GPT, один open-weights), щоб
з'ясувати, чи 100% trajectory false-green rate є властивістю одного тиру чи
всіх. Це найсильніший матеріал для другого флагмана.
