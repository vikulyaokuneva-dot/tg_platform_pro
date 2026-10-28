# PETS — расследование исторической партии из 30 кандидатов

Дата аудита: 2026-10-28  
Режим: read-only. Новый поиск, GigaChat, Telegram/VK, изменение SQLite/durable-state и настроек публикации не выполнялись.

## Что удалось восстановить

Исторический артефакт `runs/pets_3_1_3_artifact/pets_source_candidates.json` подтверждает партию из **30 уникальных** записей. Однако его формат сохранил только 1 `editorially_ready` и 9 `review_candidates`; отдельные данные оставшихся 20 записей в JSON отсутствуют.

Проверены локальные ожидаемые temporary SQLite (`tmp_out/pets_3_1_3_*.sqlite`), `data/pets_source_candidates.db`, durable-state ветки `pets-state` и метаданные сохранённых GitHub Actions artifacts. Полная временная SQLite партии не найдена; в актуальном durable-state таблица `pets_source_candidates` содержит 0 строк. Поэтому ниже 10 карточек восстановлены по первичным данным, а 20 записей честно обозначены как невосстановимые — без придуманных названий, ссылок и причин.

| Источник | Найдено | Уникально | Editorially ready | Needs review |
|---|---:|---:|---:|---:|
| fda_cvm | 9 | 9 | 0 | 9 |
| frontiers_vet | 9 | 9 | 0 | 9 |
| pmc_oa | 13 | 12 | 1 | 11 |

## Все 30 записей

### 01. Is the Cat–Owner Relationship Related to Cat–Wildlife Conflicts?

- **Восстановление:** восстановлен из runs/pets_3_1_3_artifact/pets_source_candidates.json
- **ID / источник:** `pmc:PMC13565001` / pmc_oa
- **Оригинал:** https://pmc.ncbi.nlm.nih.gov/articles/PMC13565001/
- **DOI / вид:** 10.3390/ani16172777 / cat
- **Содержательный фрагмент:** Different to our predictions, we found no evidence of a negative correlation between the cat–owner relationship and the cats’ video-evidenced exploration and hunting behaviors; neither did intrinsic or husbandry-related factors matter.
- **Сохранённые полезные факты (4):** Different to our predictions, we found no evidence of a negative correlation between the cat–owner relationship and the cats’ video-evidenced exploration and hunting behaviors; neither did intrinsic or husbandry-related factors matter. | Individual variability in the frequency of hunting-related behaviors was indeed a highly significant result in our study (Figure 4a). | Different from hunting behaviors and preference for urban or more natural environmental settings, the cats’ exploration patterns were relatively uniform but deserve attention, as they were the most frequently displayed behaviors (considering the mean values, measured both as point events and for state event behaviors; Figure 3). | Indeed, one of our detected trends showed that cats whose owners reported hunting exhibited higher levels of exploratory behaviors.
- **Статус:** technical=source_usable; safety=candidate_ready; editorial=editorially_ready; score=14/14.
- **Фильтр / точная причина:** editorial_assessment / editorial gate — Нет: editorially_ready..
- **Лицензия:** CC_BY; адаптация: да.
- **Изображение:** Фото не выбрано; поиск потенциально возможен; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **A — пригоден**. Домашний контекст, четыре прослеживаемых факта, CC BY; выводы нужно оставить в рамках опроса.
- **Перспектива GigaChat:** Да: factual brief уже достаточно полный; сохранить ограничения survey и не делать универсальных рекомендаций.
- **Обязательные проверки:** Фактологическая проверка, тематическая лицензированная фотография, ручная редактура выводов.
- **Ограничения исследования/восстановления:** The selected source is study-specific; its findings are not a universal owner recommendation.

### 02. Investigating the effect a single dose of cannabidiol has on measures of stress in cats when being transported in a carrier and meeting a novel person in an unfamiliar environment

- **Восстановление:** восстановлен из runs/pets_3_1_3_artifact/pets_source_candidates.json
- **ID / источник:** `pmc:PMC11571322` / frontiers_vet
- **Оригинал:** https://pmc.ncbi.nlm.nih.gov/articles/PMC11571322/
- **DOI / вид:** 10.3389/fvets.2024.1476296 / cat
- **Содержательный фрагмент:** Serum cortisol significantly increased after exposure to the stress paradigm, suggesting that these events were stressful for this population of cats.
- **Сохранённые полезные факты (5):** Serum cortisol significantly increased after exposure to the stress paradigm, suggesting that these events were stressful for this population of cats. | No significant differences in mean or maximum HR were observed between either portion of the stress paradigm. | Reduced HRV has been considered to represent a more negative emotional state in dogs (38), which may suggest that cats provided with CBD had a more positive experience during the “novel person in an unfamiliar test environment” portion of the stress paradigm than they did in the “carrier travel” portion. | It should be noted, however, that the estimated means for both mean and maximum HR throughout this study (mean HR; x¯ = 86 ± SD 16 beats/min, maximum HR = x¯ 102 ± SD 16 beats/min) were comparatively low compared to what is typically expected for cats within a non-stressful home environment, as measured using an electrocardiogram (mean HR: x¯ = 132 ± SD19 beats/min; (39)). | In addition to HR, no significant effect of treatment was observed for any of the behavioural metrics collected.
- **Статус:** technical=source_usable; safety=review; editorial=needs_editorial_review; score=12/14.
- **Фильтр / точная причина:** editorial_assessment / editorial gate — safety: medical_or_sensitive=treatment.
- **Лицензия:** CC_BY; адаптация: да.
- **Изображение:** Фото не выбрано; поиск потенциально возможен; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **C — непригоден**. Исследование про CBD и стресс; материал относится к лечению/чувствительной ветеринарной теме.
- **Перспектива GigaChat:** Нет для обычного автопоста: текущий factual brief нельзя превращать в совет владельцу.
- **Обязательные проверки:** Сохранять medical gate; возможен только отдельный экспертный медицинский формат.
- **Ограничения исследования/восстановления:** The selected source is study-specific; its findings are not a universal owner recommendation.

### 03. Chronic enteropathy in dogs affects the quality of life in both dogs and their owners—are veterinarians proficient in handling the caregiver burden?

- **Восстановление:** восстановлен из runs/pets_3_1_3_artifact/pets_source_candidates.json
- **ID / источник:** `pmc:PMC11747720` / frontiers_vet
- **Оригинал:** https://pmc.ncbi.nlm.nih.gov/articles/PMC11747720/
- **DOI / вид:** 10.3389/fvets.2024.1488917 / dog
- **Содержательный фрагмент:** Содержательный фрагмент не сохранён: 0 извлечённых фактов.
- **Сохранённые полезные факты (0):** Не сохранены: extractor не выделил пригодных evidence-pattern facts.
- **Статус:** technical=source_usable; safety=candidate_ready; editorial=needs_editorial_review; score=8/14.
- **Фильтр / точная причина:** editorial_assessment / editorial gate — facts: fewer than three evidence-pattern facts; evidence: no result/discussion/conclusion fact; plain_language: no concise evidence statements.
- **Лицензия:** CC_BY; адаптация: да.
- **Изображение:** Фото не выбрано; поиск потенциально возможен; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **B — требует доработки**. Тема нагрузки на владельца потенциально полезна, но сохранённый набор не содержит фактов для поста.
- **Перспектива GigaChat:** Только после добавления подтверждённых, немедицинских фактов и чёткого ограничения темы.
- **Обязательные проверки:** Минимум 3 трассируемых факта; не давать советов по лечению хронической энтеропатии.
- **Ограничения исследования/восстановления:** One limitation of the methods employed in this study is that owners and veterinarians were not paired.; The authors of this study could have interviewed owners who used one of the veterinarians interviewed in the study as their local practice, but such owner-veterinarian pairings were not pursued.

### 04. Common recorded diagnoses in purebred vs. mixed-breed dogs: a multivariable analysis of primary-care electronic medical records in South Korea

- **Восстановление:** восстановлен из runs/pets_3_1_3_artifact/pets_source_candidates.json
- **ID / источник:** `pmc:PMC13533715` / frontiers_vet
- **Оригинал:** https://pmc.ncbi.nlm.nih.gov/articles/PMC13533715/
- **DOI / вид:** 10.3389/fvets.2026.1925257 / dog
- **Содержательный фрагмент:** Because the cohort was dominated by small-breed dogs and the analyses could not fully account for body size, follow-up duration, detection bias, or diagnostic-coding heterogeneity, the observed associations may reflect breed composition, morphology, owner behavior, healthcare access, and recording practices in addition to underlying biological differences.
- **Сохранённые полезные факты (2):** Because the cohort was dominated by small-breed dogs and the analyses could not fully account for body size, follow-up duration, detection bias, or diagnostic-coding heterogeneity, the observed associations may reflect breed composition, morphology, owner behavior, healthcare access, and recording practices in addition to underlying biological differences. | Accordingly, the observed differences may reflect breed composition, morphology, owner behavior, healthcare access, and diagnostic or coding practices, in addition to any underlying biological factors.
- **Статус:** technical=source_usable; safety=review; editorial=needs_editorial_review; score=6/14.
- **Фильтр / точная причина:** editorial_assessment / editorial gate — owner_relevance: excluded=diagnos; domestic_context=True; facts: fewer than three evidence-pattern facts; safety: medical_or_sensitive=diagnos; image: a relevant photo search is not feasible.
- **Лицензия:** CC_BY; адаптация: да.
- **Изображение:** Фото не выбрано; в этом запуске поиск не признан подходящим; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **C — непригоден**. Диагнозы из медицинских карт и узкий контекст первичной ветеринарной помощи; не тема бытового поста.
- **Перспектива GigaChat:** Нет: генерация не устранит медицинский риск и слабую применимость.
- **Обязательные проверки:** Сохранять medical/audience gate.
- **Ограничения исследования/восстановления:** Several limitations should be considered when interpreting these findings.; First, breed type was based on owner-reported and clinician-recorded EMR entries rather than genetic testing, so some degree of misclassification is possible.

### 05. Cross-Sectional Age Differences in Canine Personality Traits; Influence of Breed, Sex, Previous Trauma, and Dog Obedience Tasks

- **Восстановление:** восстановлен из runs/pets_3_1_3_artifact/pets_source_candidates.json
- **ID / источник:** `pmc:PMC6971055` / frontiers_vet
- **Оригинал:** https://pmc.ncbi.nlm.nih.gov/articles/PMC6971055/
- **DOI / вид:** 10.3389/fvets.2019.00493 / dog
- **Содержательный фрагмент:** Younger dogs had higher Activity/Excitability levels than older dogs, while older dogs had lower Responsiveness to training.
- **Сохранённые полезные факты (5):** Younger dogs had higher Activity/Excitability levels than older dogs, while older dogs had lower Responsiveness to training. | This finding is likely to be caused by compensatory behavioral changes to biological aging (64), and also could be influenced by the owner's attitude to their aging dog [geriatric dogs received less activity/interaction/training with the owner than other age groups (56)]. | The most important factors that influenced personality traits (that had a higher than 1% variance explained) were age, weight, breed (pure breed or mixed breed), sex, off-leash activity, diet, previous trauma, age of the dog when it first arrived in the household, number of dog obedience tasks the dog could perform, time spent in play/interacting with owner, number of known commands, and current dog training activities. | Unsurprisingly, the factor Activity/Excitability, which contains the facets Excitability, Playfulness, Active Engagement and Companionability, showed a strong decline with age in the current cross-sectional study. | Several studies have reported decreases in activity levels with age in dogs within the home environment (84, 85).
- **Статус:** technical=source_usable; safety=candidate_ready; editorial=needs_editorial_review; score=12/14.
- **Фильтр / точная причина:** editorial_assessment / editorial gate — plain_language: no concise evidence statements.
- **Лицензия:** CC_BY; адаптация: да.
- **Изображение:** Фото не выбрано; поиск потенциально возможен; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **B — требует доработки**. Возрастные изменения активности и взаимодействия с владельцем полезны, но выводы исследования нельзя подавать как норму для каждой собаки.
- **Перспектива GigaChat:** Да, после выделения 3–5 кратких фактов и явного ограничения: cross-sectional survey, не причинный вывод.
- **Обязательные проверки:** Проверить несоответствие лога `plain_language`; сохранить возрастные и выборочные ограничения.
- **Ограничения исследования/восстановления:** The selected source is study-specific; its findings are not a universal owner recommendation.

### 06. Comparative Study of Free-Roaming Domestic Dog Management and Roaming Behavior Across Four Countries: Chad, Guatemala, Indonesia, and Uganda

- **Восстановление:** восстановлен из runs/pets_3_1_3_artifact/pets_source_candidates.json
- **ID / источник:** `pmc:PMC7970034` / frontiers_vet
- **Оригинал:** https://pmc.ncbi.nlm.nih.gov/articles/PMC7970034/
- **DOI / вид:** 10.3389/fvets.2021.617900 / dog
- **Содержательный фрагмент:** Senior dogs had smaller home ranges in Uganda, which could be explained by lower activity levels in older dogs.
- **Сохранённые полезные факты (3):** Senior dogs had smaller home ranges in Uganda, which could be explained by lower activity levels in older dogs. | This is supported by a study in Mexico, where dogs scavenging turtle nests had lower food metabolic intake provided by their owners and larger activity ranges (12). | We explored whether excluding of dogs with <48 h of data collection, that is, those dogs with <2 daytime periods recorded, displayed differences in the identification of factors influencing the home range size.
- **Статус:** technical=source_usable; safety=candidate_ready; editorial=needs_editorial_review; score=10/14.
- **Фильтр / точная причина:** editorial_assessment / editorial gate — owner_relevance: excluded=free-roaming; domestic_context=True; image: a relevant photo search is not feasible.
- **Лицензия:** CC_BY; адаптация: да.
- **Изображение:** Фото не выбрано; в этом запуске поиск не признан подходящим; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **C — непригоден**. Свободно гуляющие собаки в четырёх странах — не подтверждённый контекст обычного владельца домашней собаки.
- **Перспектива GigaChat:** Нет для текущей очереди: полезный общий вывод не сохранён и переносить результаты нельзя.
- **Обязательные проверки:** Сохранять audience gate; не делать обобщений по другой популяции.
- **Ограничения исследования/восстановления:** The selected source is study-specific; its findings are not a universal owner recommendation.

### 07. Did the COVID-19 Pandemic Spark a Public Interest in Pet Adoption?

- **Восстановление:** восстановлен из runs/pets_3_1_3_artifact/pets_source_candidates.json
- **ID / источник:** `pmc:PMC8145284` / frontiers_vet
- **Оригинал:** https://pmc.ncbi.nlm.nih.gov/articles/PMC8145284/
- **DOI / вид:** 10.3389/fvets.2021.647308 / both
- **Содержательный фрагмент:** Содержательный фрагмент не сохранён: 0 извлечённых фактов.
- **Сохранённые полезные факты (0):** Не сохранены: extractor не выделил пригодных evidence-pattern facts.
- **Статус:** technical=source_usable; safety=candidate_ready; editorial=needs_editorial_review; score=8/14.
- **Фильтр / точная причина:** editorial_assessment / editorial gate — facts: fewer than three evidence-pattern facts; evidence: no result/discussion/conclusion fact; plain_language: no concise evidence statements.
- **Лицензия:** CC_BY; адаптация: да.
- **Изображение:** Фото не выбрано; поиск потенциально возможен; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **B — требует доработки**. Интерес к усыновлению питомцев может стать темой о подготовке дома, но исторический extract не сохранил содержательных фактов.
- **Перспектива GigaChat:** Только после новых подтверждённых фактов и практического, не медицинского ракурса.
- **Обязательные проверки:** Минимум 3 факта, проверка на актуальность и отсутствие подмены общественного интереса советом владельцу.
- **Ограничения исследования/восстановления:** The selected source is study-specific; its findings are not a universal owner recommendation.

### 08. Benefits and risks of staff-owned dogs in small animal clinics: perspectives of employees that bring their dog to work

- **Восстановление:** восстановлен из runs/pets_3_1_3_artifact/pets_source_candidates.json
- **ID / источник:** `pmc:PMC13383378` / frontiers_vet
- **Оригинал:** https://pmc.ncbi.nlm.nih.gov/articles/PMC13383378/
- **DOI / вид:** 10.3389/fvets.2026.1867788 / dog
- **Содержательный фрагмент:** In academic settings, staff-owned dogs were also commonly used for hands-on student training and as healthy controls in clinical trials (14).
- **Сохранённые полезные факты (1):** In academic settings, staff-owned dogs were also commonly used for hands-on student training and as healthy controls in clinical trials (14).
- **Статус:** technical=source_usable; safety=review; editorial=needs_editorial_review; score=10/14.
- **Фильтр / точная причина:** editorial_assessment / editorial gate — facts: fewer than three evidence-pattern facts; safety: medical_or_sensitive=clinical; sample: population is too narrow for a general owner-facing brief.
- **Лицензия:** CC_BY; адаптация: да.
- **Изображение:** Фото не выбрано; поиск потенциально возможен; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **C — непригоден**. Собаки сотрудников в ветеринарных клиниках: узкая профессиональная выборка и клинический контекст.
- **Перспектива GigaChat:** Нет: генерация не сделает тему массовой и безопасной для владельцев.
- **Обязательные проверки:** Сохранять medical/specialist-sample gate.
- **Ограничения исследования/восстановления:** The selected source is study-specific; its findings are not a universal owner recommendation.

### 09. A comparison of owner perceived and measured body condition, feeding and exercise in sport and pet dogs

- **Восстановление:** восстановлен из runs/pets_3_1_3_artifact/pets_source_candidates.json
- **ID / источник:** `pmc:PMC10600488` / frontiers_vet
- **Оригинал:** https://pmc.ncbi.nlm.nih.gov/articles/PMC10600488/
- **DOI / вид:** 10.3389/fvets.2023.1211996 / dog
- **Содержательный фрагмент:** Dog exercise was consistent across groups and suggested that owners walked with their dogs most days of the week for 15 to 45 min.
- **Сохранённые полезные факты (1):** Dog exercise was consistent across groups and suggested that owners walked with their dogs most days of the week for 15 to 45 min.
- **Статус:** technical=source_usable; safety=candidate_ready; editorial=needs_editorial_review; score=8/14.
- **Фильтр / точная причина:** editorial_assessment / editorial gate — owner_relevance: excluded=body condition; domestic_context=True; facts: fewer than three evidence-pattern facts; image: a relevant photo search is not feasible.
- **Лицензия:** CC_BY; адаптация: да.
- **Изображение:** Фото не выбрано; в этом запуске поиск не признан подходящим; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **B — требует доработки**. Есть бытовой сигнал о регулярных прогулках, но один факт и тема body condition требуют дополнительных безопасных источников.
- **Перспектива GigaChat:** Да, лишь после подготовки нейтрального поста о режиме прогулок без медицинских выводов о весе.
- **Обязательные проверки:** Добавить факты; не превращать опрос в норму или рекомендацию по весу/питанию.
- **Ограничения исследования/восстановления:** The anthropometric measurements in this study were taken by the owner rather than a researcher due to the questionnaire based nature of the study.; It is possible that owners made measurement errors in determining the pelvic circumference and hock to stifle length.

### 10. The Interplay Between Affect, Dog's Physical Activity and Dog–Owner Relationship

- **Восстановление:** восстановлен из runs/pets_3_1_3_artifact/pets_source_candidates.json
- **ID / источник:** `pmc:PMC8695727` / frontiers_vet
- **Оригинал:** https://pmc.ncbi.nlm.nih.gov/articles/PMC8695727/
- **DOI / вид:** 10.3389/fvets.2021.673407 / dog
- **Содержательный фрагмент:** Our findings showed some positive associations between activity measurements, questionnaire, and rating scale data.
- **Сохранённые полезные факты (2):** Our findings showed some positive associations between activity measurements, questionnaire, and rating scale data. | The daily and daytime activity levels of the dog were related to the affective experiences of the dog and owner when the dog was left home alone.
- **Статус:** technical=source_usable; safety=candidate_ready; editorial=needs_editorial_review; score=12/14.
- **Фильтр / точная причина:** editorial_assessment / editorial gate — facts: fewer than three evidence-pattern facts.
- **Лицензия:** CC_BY; адаптация: да.
- **Изображение:** Фото не выбрано; поиск потенциально возможен; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **B — требует доработки**. Связь активности, эмоционального состояния и отношений с владельцем интересна, но сохранены только два факта и небольшая выборка.
- **Перспектива GigaChat:** Да, после дополнительной проверки: пост о наблюдении и спокойной активности, без причинных утверждений.
- **Обязательные проверки:** Минимум 3 факта, малая выборка N=19, не путать ассоциацию с причинностью.
- **Ограничения исследования/восстановления:** The number of participants in this study was fairly small.; It is also likely that active dog owners who have strong emotional relationships with their dogs and who are interested in the welfare of their dogs will volunteer in this kind of study.

### 11. не сохранено

- **Восстановление:** не восстановлен: сохранилась только агрегированная статистика партии
- **ID / источник:** `не установлен` / не установлен (агрегат партии: 9 Frontiers, 12 PMC OA, 9 FDA CVM)
- **Оригинал:** не сохранено
- **DOI / вид:** не сохранено / не сохранено
- **Содержательный фрагмент:** не сохранено
- **Сохранённые полезные факты (не установлено):** не сохранено
- **Статус:** technical=не установлено; safety=не установлено; editorial=не установлено; score=не установлено.
- **Фильтр / точная причина:** не установлено — не установлена: этот индивидуальный кандидат не попал в итоговый JSON и его временная SQLite не найдена.
- **Лицензия:** не установлена; адаптация: не установлена.
- **Изображение:** не установлено; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **не установлена**. Нельзя оценить содержание без названия, ссылки и extracted facts.
- **Перспектива GigaChat:** Нельзя передавать: factual brief не восстановлен.
- **Обязательные проверки:** Сначала восстановить первичную запись; не создавать её заново поиском.
- **Ограничения исследования/восстановления:** Запись утрачена историческим форматом отчёта.

### 12. не сохранено

- **Восстановление:** не восстановлен: сохранилась только агрегированная статистика партии
- **ID / источник:** `не установлен` / не установлен (агрегат партии: 9 Frontiers, 12 PMC OA, 9 FDA CVM)
- **Оригинал:** не сохранено
- **DOI / вид:** не сохранено / не сохранено
- **Содержательный фрагмент:** не сохранено
- **Сохранённые полезные факты (не установлено):** не сохранено
- **Статус:** technical=не установлено; safety=не установлено; editorial=не установлено; score=не установлено.
- **Фильтр / точная причина:** не установлено — не установлена: этот индивидуальный кандидат не попал в итоговый JSON и его временная SQLite не найдена.
- **Лицензия:** не установлена; адаптация: не установлена.
- **Изображение:** не установлено; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **не установлена**. Нельзя оценить содержание без названия, ссылки и extracted facts.
- **Перспектива GigaChat:** Нельзя передавать: factual brief не восстановлен.
- **Обязательные проверки:** Сначала восстановить первичную запись; не создавать её заново поиском.
- **Ограничения исследования/восстановления:** Запись утрачена историческим форматом отчёта.

### 13. не сохранено

- **Восстановление:** не восстановлен: сохранилась только агрегированная статистика партии
- **ID / источник:** `не установлен` / не установлен (агрегат партии: 9 Frontiers, 12 PMC OA, 9 FDA CVM)
- **Оригинал:** не сохранено
- **DOI / вид:** не сохранено / не сохранено
- **Содержательный фрагмент:** не сохранено
- **Сохранённые полезные факты (не установлено):** не сохранено
- **Статус:** technical=не установлено; safety=не установлено; editorial=не установлено; score=не установлено.
- **Фильтр / точная причина:** не установлено — не установлена: этот индивидуальный кандидат не попал в итоговый JSON и его временная SQLite не найдена.
- **Лицензия:** не установлена; адаптация: не установлена.
- **Изображение:** не установлено; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **не установлена**. Нельзя оценить содержание без названия, ссылки и extracted facts.
- **Перспектива GigaChat:** Нельзя передавать: factual brief не восстановлен.
- **Обязательные проверки:** Сначала восстановить первичную запись; не создавать её заново поиском.
- **Ограничения исследования/восстановления:** Запись утрачена историческим форматом отчёта.

### 14. не сохранено

- **Восстановление:** не восстановлен: сохранилась только агрегированная статистика партии
- **ID / источник:** `не установлен` / не установлен (агрегат партии: 9 Frontiers, 12 PMC OA, 9 FDA CVM)
- **Оригинал:** не сохранено
- **DOI / вид:** не сохранено / не сохранено
- **Содержательный фрагмент:** не сохранено
- **Сохранённые полезные факты (не установлено):** не сохранено
- **Статус:** technical=не установлено; safety=не установлено; editorial=не установлено; score=не установлено.
- **Фильтр / точная причина:** не установлено — не установлена: этот индивидуальный кандидат не попал в итоговый JSON и его временная SQLite не найдена.
- **Лицензия:** не установлена; адаптация: не установлена.
- **Изображение:** не установлено; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **не установлена**. Нельзя оценить содержание без названия, ссылки и extracted facts.
- **Перспектива GigaChat:** Нельзя передавать: factual brief не восстановлен.
- **Обязательные проверки:** Сначала восстановить первичную запись; не создавать её заново поиском.
- **Ограничения исследования/восстановления:** Запись утрачена историческим форматом отчёта.

### 15. не сохранено

- **Восстановление:** не восстановлен: сохранилась только агрегированная статистика партии
- **ID / источник:** `не установлен` / не установлен (агрегат партии: 9 Frontiers, 12 PMC OA, 9 FDA CVM)
- **Оригинал:** не сохранено
- **DOI / вид:** не сохранено / не сохранено
- **Содержательный фрагмент:** не сохранено
- **Сохранённые полезные факты (не установлено):** не сохранено
- **Статус:** technical=не установлено; safety=не установлено; editorial=не установлено; score=не установлено.
- **Фильтр / точная причина:** не установлено — не установлена: этот индивидуальный кандидат не попал в итоговый JSON и его временная SQLite не найдена.
- **Лицензия:** не установлена; адаптация: не установлена.
- **Изображение:** не установлено; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **не установлена**. Нельзя оценить содержание без названия, ссылки и extracted facts.
- **Перспектива GigaChat:** Нельзя передавать: factual brief не восстановлен.
- **Обязательные проверки:** Сначала восстановить первичную запись; не создавать её заново поиском.
- **Ограничения исследования/восстановления:** Запись утрачена историческим форматом отчёта.

### 16. не сохранено

- **Восстановление:** не восстановлен: сохранилась только агрегированная статистика партии
- **ID / источник:** `не установлен` / не установлен (агрегат партии: 9 Frontiers, 12 PMC OA, 9 FDA CVM)
- **Оригинал:** не сохранено
- **DOI / вид:** не сохранено / не сохранено
- **Содержательный фрагмент:** не сохранено
- **Сохранённые полезные факты (не установлено):** не сохранено
- **Статус:** technical=не установлено; safety=не установлено; editorial=не установлено; score=не установлено.
- **Фильтр / точная причина:** не установлено — не установлена: этот индивидуальный кандидат не попал в итоговый JSON и его временная SQLite не найдена.
- **Лицензия:** не установлена; адаптация: не установлена.
- **Изображение:** не установлено; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **не установлена**. Нельзя оценить содержание без названия, ссылки и extracted facts.
- **Перспектива GigaChat:** Нельзя передавать: factual brief не восстановлен.
- **Обязательные проверки:** Сначала восстановить первичную запись; не создавать её заново поиском.
- **Ограничения исследования/восстановления:** Запись утрачена историческим форматом отчёта.

### 17. не сохранено

- **Восстановление:** не восстановлен: сохранилась только агрегированная статистика партии
- **ID / источник:** `не установлен` / не установлен (агрегат партии: 9 Frontiers, 12 PMC OA, 9 FDA CVM)
- **Оригинал:** не сохранено
- **DOI / вид:** не сохранено / не сохранено
- **Содержательный фрагмент:** не сохранено
- **Сохранённые полезные факты (не установлено):** не сохранено
- **Статус:** technical=не установлено; safety=не установлено; editorial=не установлено; score=не установлено.
- **Фильтр / точная причина:** не установлено — не установлена: этот индивидуальный кандидат не попал в итоговый JSON и его временная SQLite не найдена.
- **Лицензия:** не установлена; адаптация: не установлена.
- **Изображение:** не установлено; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **не установлена**. Нельзя оценить содержание без названия, ссылки и extracted facts.
- **Перспектива GigaChat:** Нельзя передавать: factual brief не восстановлен.
- **Обязательные проверки:** Сначала восстановить первичную запись; не создавать её заново поиском.
- **Ограничения исследования/восстановления:** Запись утрачена историческим форматом отчёта.

### 18. не сохранено

- **Восстановление:** не восстановлен: сохранилась только агрегированная статистика партии
- **ID / источник:** `не установлен` / не установлен (агрегат партии: 9 Frontiers, 12 PMC OA, 9 FDA CVM)
- **Оригинал:** не сохранено
- **DOI / вид:** не сохранено / не сохранено
- **Содержательный фрагмент:** не сохранено
- **Сохранённые полезные факты (не установлено):** не сохранено
- **Статус:** technical=не установлено; safety=не установлено; editorial=не установлено; score=не установлено.
- **Фильтр / точная причина:** не установлено — не установлена: этот индивидуальный кандидат не попал в итоговый JSON и его временная SQLite не найдена.
- **Лицензия:** не установлена; адаптация: не установлена.
- **Изображение:** не установлено; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **не установлена**. Нельзя оценить содержание без названия, ссылки и extracted facts.
- **Перспектива GigaChat:** Нельзя передавать: factual brief не восстановлен.
- **Обязательные проверки:** Сначала восстановить первичную запись; не создавать её заново поиском.
- **Ограничения исследования/восстановления:** Запись утрачена историческим форматом отчёта.

### 19. не сохранено

- **Восстановление:** не восстановлен: сохранилась только агрегированная статистика партии
- **ID / источник:** `не установлен` / не установлен (агрегат партии: 9 Frontiers, 12 PMC OA, 9 FDA CVM)
- **Оригинал:** не сохранено
- **DOI / вид:** не сохранено / не сохранено
- **Содержательный фрагмент:** не сохранено
- **Сохранённые полезные факты (не установлено):** не сохранено
- **Статус:** technical=не установлено; safety=не установлено; editorial=не установлено; score=не установлено.
- **Фильтр / точная причина:** не установлено — не установлена: этот индивидуальный кандидат не попал в итоговый JSON и его временная SQLite не найдена.
- **Лицензия:** не установлена; адаптация: не установлена.
- **Изображение:** не установлено; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **не установлена**. Нельзя оценить содержание без названия, ссылки и extracted facts.
- **Перспектива GigaChat:** Нельзя передавать: factual brief не восстановлен.
- **Обязательные проверки:** Сначала восстановить первичную запись; не создавать её заново поиском.
- **Ограничения исследования/восстановления:** Запись утрачена историческим форматом отчёта.

### 20. не сохранено

- **Восстановление:** не восстановлен: сохранилась только агрегированная статистика партии
- **ID / источник:** `не установлен` / не установлен (агрегат партии: 9 Frontiers, 12 PMC OA, 9 FDA CVM)
- **Оригинал:** не сохранено
- **DOI / вид:** не сохранено / не сохранено
- **Содержательный фрагмент:** не сохранено
- **Сохранённые полезные факты (не установлено):** не сохранено
- **Статус:** technical=не установлено; safety=не установлено; editorial=не установлено; score=не установлено.
- **Фильтр / точная причина:** не установлено — не установлена: этот индивидуальный кандидат не попал в итоговый JSON и его временная SQLite не найдена.
- **Лицензия:** не установлена; адаптация: не установлена.
- **Изображение:** не установлено; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **не установлена**. Нельзя оценить содержание без названия, ссылки и extracted facts.
- **Перспектива GigaChat:** Нельзя передавать: factual brief не восстановлен.
- **Обязательные проверки:** Сначала восстановить первичную запись; не создавать её заново поиском.
- **Ограничения исследования/восстановления:** Запись утрачена историческим форматом отчёта.

### 21. не сохранено

- **Восстановление:** не восстановлен: сохранилась только агрегированная статистика партии
- **ID / источник:** `не установлен` / не установлен (агрегат партии: 9 Frontiers, 12 PMC OA, 9 FDA CVM)
- **Оригинал:** не сохранено
- **DOI / вид:** не сохранено / не сохранено
- **Содержательный фрагмент:** не сохранено
- **Сохранённые полезные факты (не установлено):** не сохранено
- **Статус:** technical=не установлено; safety=не установлено; editorial=не установлено; score=не установлено.
- **Фильтр / точная причина:** не установлено — не установлена: этот индивидуальный кандидат не попал в итоговый JSON и его временная SQLite не найдена.
- **Лицензия:** не установлена; адаптация: не установлена.
- **Изображение:** не установлено; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **не установлена**. Нельзя оценить содержание без названия, ссылки и extracted facts.
- **Перспектива GigaChat:** Нельзя передавать: factual brief не восстановлен.
- **Обязательные проверки:** Сначала восстановить первичную запись; не создавать её заново поиском.
- **Ограничения исследования/восстановления:** Запись утрачена историческим форматом отчёта.

### 22. не сохранено

- **Восстановление:** не восстановлен: сохранилась только агрегированная статистика партии
- **ID / источник:** `не установлен` / не установлен (агрегат партии: 9 Frontiers, 12 PMC OA, 9 FDA CVM)
- **Оригинал:** не сохранено
- **DOI / вид:** не сохранено / не сохранено
- **Содержательный фрагмент:** не сохранено
- **Сохранённые полезные факты (не установлено):** не сохранено
- **Статус:** technical=не установлено; safety=не установлено; editorial=не установлено; score=не установлено.
- **Фильтр / точная причина:** не установлено — не установлена: этот индивидуальный кандидат не попал в итоговый JSON и его временная SQLite не найдена.
- **Лицензия:** не установлена; адаптация: не установлена.
- **Изображение:** не установлено; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **не установлена**. Нельзя оценить содержание без названия, ссылки и extracted facts.
- **Перспектива GigaChat:** Нельзя передавать: factual brief не восстановлен.
- **Обязательные проверки:** Сначала восстановить первичную запись; не создавать её заново поиском.
- **Ограничения исследования/восстановления:** Запись утрачена историческим форматом отчёта.

### 23. не сохранено

- **Восстановление:** не восстановлен: сохранилась только агрегированная статистика партии
- **ID / источник:** `не установлен` / не установлен (агрегат партии: 9 Frontiers, 12 PMC OA, 9 FDA CVM)
- **Оригинал:** не сохранено
- **DOI / вид:** не сохранено / не сохранено
- **Содержательный фрагмент:** не сохранено
- **Сохранённые полезные факты (не установлено):** не сохранено
- **Статус:** technical=не установлено; safety=не установлено; editorial=не установлено; score=не установлено.
- **Фильтр / точная причина:** не установлено — не установлена: этот индивидуальный кандидат не попал в итоговый JSON и его временная SQLite не найдена.
- **Лицензия:** не установлена; адаптация: не установлена.
- **Изображение:** не установлено; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **не установлена**. Нельзя оценить содержание без названия, ссылки и extracted facts.
- **Перспектива GigaChat:** Нельзя передавать: factual brief не восстановлен.
- **Обязательные проверки:** Сначала восстановить первичную запись; не создавать её заново поиском.
- **Ограничения исследования/восстановления:** Запись утрачена историческим форматом отчёта.

### 24. не сохранено

- **Восстановление:** не восстановлен: сохранилась только агрегированная статистика партии
- **ID / источник:** `не установлен` / не установлен (агрегат партии: 9 Frontiers, 12 PMC OA, 9 FDA CVM)
- **Оригинал:** не сохранено
- **DOI / вид:** не сохранено / не сохранено
- **Содержательный фрагмент:** не сохранено
- **Сохранённые полезные факты (не установлено):** не сохранено
- **Статус:** technical=не установлено; safety=не установлено; editorial=не установлено; score=не установлено.
- **Фильтр / точная причина:** не установлено — не установлена: этот индивидуальный кандидат не попал в итоговый JSON и его временная SQLite не найдена.
- **Лицензия:** не установлена; адаптация: не установлена.
- **Изображение:** не установлено; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **не установлена**. Нельзя оценить содержание без названия, ссылки и extracted facts.
- **Перспектива GigaChat:** Нельзя передавать: factual brief не восстановлен.
- **Обязательные проверки:** Сначала восстановить первичную запись; не создавать её заново поиском.
- **Ограничения исследования/восстановления:** Запись утрачена историческим форматом отчёта.

### 25. не сохранено

- **Восстановление:** не восстановлен: сохранилась только агрегированная статистика партии
- **ID / источник:** `не установлен` / не установлен (агрегат партии: 9 Frontiers, 12 PMC OA, 9 FDA CVM)
- **Оригинал:** не сохранено
- **DOI / вид:** не сохранено / не сохранено
- **Содержательный фрагмент:** не сохранено
- **Сохранённые полезные факты (не установлено):** не сохранено
- **Статус:** technical=не установлено; safety=не установлено; editorial=не установлено; score=не установлено.
- **Фильтр / точная причина:** не установлено — не установлена: этот индивидуальный кандидат не попал в итоговый JSON и его временная SQLite не найдена.
- **Лицензия:** не установлена; адаптация: не установлена.
- **Изображение:** не установлено; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **не установлена**. Нельзя оценить содержание без названия, ссылки и extracted facts.
- **Перспектива GigaChat:** Нельзя передавать: factual brief не восстановлен.
- **Обязательные проверки:** Сначала восстановить первичную запись; не создавать её заново поиском.
- **Ограничения исследования/восстановления:** Запись утрачена историческим форматом отчёта.

### 26. не сохранено

- **Восстановление:** не восстановлен: сохранилась только агрегированная статистика партии
- **ID / источник:** `не установлен` / не установлен (агрегат партии: 9 Frontiers, 12 PMC OA, 9 FDA CVM)
- **Оригинал:** не сохранено
- **DOI / вид:** не сохранено / не сохранено
- **Содержательный фрагмент:** не сохранено
- **Сохранённые полезные факты (не установлено):** не сохранено
- **Статус:** technical=не установлено; safety=не установлено; editorial=не установлено; score=не установлено.
- **Фильтр / точная причина:** не установлено — не установлена: этот индивидуальный кандидат не попал в итоговый JSON и его временная SQLite не найдена.
- **Лицензия:** не установлена; адаптация: не установлена.
- **Изображение:** не установлено; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **не установлена**. Нельзя оценить содержание без названия, ссылки и extracted facts.
- **Перспектива GigaChat:** Нельзя передавать: factual brief не восстановлен.
- **Обязательные проверки:** Сначала восстановить первичную запись; не создавать её заново поиском.
- **Ограничения исследования/восстановления:** Запись утрачена историческим форматом отчёта.

### 27. не сохранено

- **Восстановление:** не восстановлен: сохранилась только агрегированная статистика партии
- **ID / источник:** `не установлен` / не установлен (агрегат партии: 9 Frontiers, 12 PMC OA, 9 FDA CVM)
- **Оригинал:** не сохранено
- **DOI / вид:** не сохранено / не сохранено
- **Содержательный фрагмент:** не сохранено
- **Сохранённые полезные факты (не установлено):** не сохранено
- **Статус:** technical=не установлено; safety=не установлено; editorial=не установлено; score=не установлено.
- **Фильтр / точная причина:** не установлено — не установлена: этот индивидуальный кандидат не попал в итоговый JSON и его временная SQLite не найдена.
- **Лицензия:** не установлена; адаптация: не установлена.
- **Изображение:** не установлено; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **не установлена**. Нельзя оценить содержание без названия, ссылки и extracted facts.
- **Перспектива GigaChat:** Нельзя передавать: factual brief не восстановлен.
- **Обязательные проверки:** Сначала восстановить первичную запись; не создавать её заново поиском.
- **Ограничения исследования/восстановления:** Запись утрачена историческим форматом отчёта.

### 28. не сохранено

- **Восстановление:** не восстановлен: сохранилась только агрегированная статистика партии
- **ID / источник:** `не установлен` / не установлен (агрегат партии: 9 Frontiers, 12 PMC OA, 9 FDA CVM)
- **Оригинал:** не сохранено
- **DOI / вид:** не сохранено / не сохранено
- **Содержательный фрагмент:** не сохранено
- **Сохранённые полезные факты (не установлено):** не сохранено
- **Статус:** technical=не установлено; safety=не установлено; editorial=не установлено; score=не установлено.
- **Фильтр / точная причина:** не установлено — не установлена: этот индивидуальный кандидат не попал в итоговый JSON и его временная SQLite не найдена.
- **Лицензия:** не установлена; адаптация: не установлена.
- **Изображение:** не установлено; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **не установлена**. Нельзя оценить содержание без названия, ссылки и extracted facts.
- **Перспектива GigaChat:** Нельзя передавать: factual brief не восстановлен.
- **Обязательные проверки:** Сначала восстановить первичную запись; не создавать её заново поиском.
- **Ограничения исследования/восстановления:** Запись утрачена историческим форматом отчёта.

### 29. не сохранено

- **Восстановление:** не восстановлен: сохранилась только агрегированная статистика партии
- **ID / источник:** `не установлен` / не установлен (агрегат партии: 9 Frontiers, 12 PMC OA, 9 FDA CVM)
- **Оригинал:** не сохранено
- **DOI / вид:** не сохранено / не сохранено
- **Содержательный фрагмент:** не сохранено
- **Сохранённые полезные факты (не установлено):** не сохранено
- **Статус:** technical=не установлено; safety=не установлено; editorial=не установлено; score=не установлено.
- **Фильтр / точная причина:** не установлено — не установлена: этот индивидуальный кандидат не попал в итоговый JSON и его временная SQLite не найдена.
- **Лицензия:** не установлена; адаптация: не установлена.
- **Изображение:** не установлено; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **не установлена**. Нельзя оценить содержание без названия, ссылки и extracted facts.
- **Перспектива GigaChat:** Нельзя передавать: factual brief не восстановлен.
- **Обязательные проверки:** Сначала восстановить первичную запись; не создавать её заново поиском.
- **Ограничения исследования/восстановления:** Запись утрачена историческим форматом отчёта.

### 30. не сохранено

- **Восстановление:** не восстановлен: сохранилась только агрегированная статистика партии
- **ID / источник:** `не установлен` / не установлен (агрегат партии: 9 Frontiers, 12 PMC OA, 9 FDA CVM)
- **Оригинал:** не сохранено
- **DOI / вид:** не сохранено / не сохранено
- **Содержательный фрагмент:** не сохранено
- **Сохранённые полезные факты (не установлено):** не сохранено
- **Статус:** technical=не установлено; safety=не установлено; editorial=не установлено; score=не установлено.
- **Фильтр / точная причина:** не установлено — не установлена: этот индивидуальный кандидат не попал в итоговый JSON и его временная SQLite не найдена.
- **Лицензия:** не установлена; адаптация: не установлена.
- **Изображение:** не установлено; лицензия конкретного файла: не установлена.
- **Оценка содержания:** **не установлена**. Нельзя оценить содержание без названия, ссылки и extracted facts.
- **Перспектива GigaChat:** Нельзя передавать: factual brief не восстановлен.
- **Обязательные проверки:** Сначала восстановить первичную запись; не создавать её заново поиском.
- **Ограничения исследования/восстановления:** Запись утрачена историческим форматом отчёта.

## Наиболее перспективные отклонённые материалы

Только следующие пять отклонённых, но восстановленных материалов можно рассматривать для будущего GigaChat **после** пополнения factual brief; ни один из них сейчас не следует отправлять в генерацию автоматически.

| № | Материал | Почему потенциально полезен | Что обязательно добавить/сохранить |
|---:|---|---|---|
| 3 | Chronic enteropathy… caregiver burden | Возможен немедицинский ракурс поддержки владельца. | Минимум 3 факта; исключить советы по лечению. |
| 5 | Cross-Sectional Age Differences in Canine Personality Traits… | Понятная владельцу тема возраста, активности и взаимодействия. | Не делать причинных выводов; сохранять ограничения survey. |
| 7 | Did the COVID-19 Pandemic Spark a Public Interest in Pet Adoption? | Может дать тему о подготовке к появлению питомца. | Новые факты и современный практический источник. |
| 9 | A comparison of owner perceived and measured body condition… | Можно сузить до безопасной темы режима прогулок. | Дополнительные источники; без советов о весе/лечении. |
| 10 | The Interplay Between Affect, Dog's Physical Activity… | Подходит тема наблюдения за спокойной активностью собаки. | Третий факт, малая выборка N=19, без причинных утверждений. |

## Три наиболее проблемных фильтра

1. **Порог `facts >= 3` в `editorial_assessment`.** Записи №3 и №7 имеют 0 facts, №9 — 1, №10 — 2; все остаются review. Это важная защита от галлюцинаций, но №10 уже имеет содержательную тему и score 12/14, поэтому порог может задерживать потенциально хорошие материалы до дополнительного fact-check, а не обязательно делать их контентно плохими.
2. **Широкие keyword/audience исключения.** В логах №4 (`diagnos`), №6 (`free-roaming`) и №9 (`body condition`) видны причины `owner_relevance: excluded=…`; агрегированная статистика также содержит 2 `false_keyword_match`. Они не доказывают, что нужно снять фильтр, но доказывают, что после keyword-исключения нужен объяснимый ручной маршрут, а не потеря карточки.
3. **Medical/sensitive gate.** №2, №4 и №8 имеют CC BY и извлечённые факты, но блокируются медицинским/клиническим контекстом. Этот фильтр нельзя отключать для автопубликации; полезнее отделить его в ручную экспертную очередь, чтобы не смешивать «небезопасно публиковать автоматически» с «контентно бесполезно».

## Корневая проблема сохранности

Главный блокер расследования — не редакционный фильтр, а исторический формат сохранения. `collect_source_candidates()` формировал `ready + review`, после чего обрезал список до `limit` (в запуске — 10); полные 30 записей существовали только во временной SQLite. Она не была приложена к артефакту и не была сохранена в durable-state. Поэтому 20 индивидуальных причин сейчас **не установлены**.

## Итог

| Категория | Количество |
|---|---:|
| Пригодны без существенной доработки | 1 |
| Можно восстановить через GigaChat после дополнительной факт-подготовки | 5 |
| Требуют дополнительных источников отдельно от пяти перспективных | 0 |
| Действительно непригодны для обычного автопоста | 4 |
| Не удалось восстановить | 20 |

Примечание к количествам: категории «через GigaChat» и «требуют источников» описывают только 10 восстановленных записей; они не распределяют 20 утраченных кандидатов. Никакие критерии отбора этим аудитом не изменялись.
