# Фильтры, справочники, пределы, схема данных

Всё в этом файле проверено запросами к hh.ru. Где вывод — гипотеза или
логическое следствие, это помечено явно.

- [Как проверять, что фильтр работает](#как-проверять-что-фильтр-работает)
- [Текстовый поиск и его условие `exp_period`](#текстовый-поиск-и-его-условие-exp_period)
- [Навыки](#навыки)
- [Образование](#образование)
- [Регион и relocation](#регион-и-relocation)
- [Остальные фильтры](#остальные-фильтры)
- [Управление выдачей](#управление-выдачей)
- [Справочники ID](#справочники-id)
- [Потолок 5000 и нарезка](#потолок-5000-и-нарезка)
- [Фасеты](#фасеты)
- [Схема записи резюме](#схема-записи-резюме)

Базовый URL: `https://hh.ru/search/resume?<params>`.

## Как проверять, что фильтр работает

Бэкенд возвращает эхо разобранного запроса в `state.resumeSearchResult.criteria`.
Сверять отправленное с разобранным нужно всегда — так ловятся молча отброшенные
параметры (это делает `criteriaDiff`, уровень L0).

**Но эхо не доказывает, что фильтр сработал.** `text` проходит эхо и при этом не
фильтрует. Настоящая проверка — изменение `stats.totalResults` при снятии параметра
(уровень L1, `filterEfficacy`).

## Текстовый поиск и его условие `exp_period`

Текстовый поиск фильтрует. Но применяется он только тогда, когда вместе с `text`
уходит **`exp_period`**. Без этого спутника запрос принимается, текст попадает в
`criteria.text` — и выдача остаётся полной. Проверено на базе «Москва,
`relocation=living`, 365 дней»:

| Запрос | totalResults |
|---|---|
| база | 2 977 913 |
| `text=механико-математический&logic=normal&pos=education` — **без `exp_period`** | 2 977 926 |
| то же **+ `exp_period=all_time`** | **11 015** (по РФ) |
| `university=<id вуза>` | 44 456 |
| `university=<id вуза>` + текст, `pos=education`, `exp_period` | **1 684** |
| `university=<id вуза>` + тот же текст, `pos=full_text` | 1 707 |
| `text=Python&pos=keywords&exp_period=all_time` | 118 403 |
| `text=квазифакультет несуществующий&pos=education&logic=phrase` (контроль) | **0** |

Текст по факультету отсекает подавляющую часть вузовской выборки, бессмысленная
фраза — ноль, `full_text` чуть шире `education`: отбор осмысленный, а не случайное
совпадение чисел.

**Почему ловушка не даёт о себе знать.** В `searchDefaults` страницы стоит
`exp_period: "all_time"`, и интерфейс шлёт его всегда — в браузере поиск работает
и выглядит исправным. Собранный руками URL этого параметра не содержит, текст молча
выключается, а `criteria` его исправно отражает. Эхо здесь совпадает, `totalResults`
нет — ровно тот случай, ради которого существует L1.

Значение `exp_period` на текстовый отбор не влияет: `all_time` и `last_year` дают
одинаковый результат. Это условие применения текста, а не его модификатор. Enum:
`all_time`, `last_year`, `last_three_years`, `last_six_years`; тот же набор у
`filter_exp_period`, а `exp_company_size` — `any`, `small`, `medium`, `large`.

Разбирается `text` только вместе с `pos` **и** `logic`: без них в `criteria.text`
приходит пустой массив. Параметры повторяются слотами — интерфейс шлёт
`text=…&text=&logic=normal&logic=normal&pos=education&pos=full_text`, где i-й `text`
читается с i-м `pos` и i-м `logic`. Пустой слот безвреден; один слот работает так же,
как пара.

### Область поиска `pos` — полный перечень

Значения берутся из `state.resumeSearchDictionaries.pos`, подписи — из
`state.searchQueries.trls.pos`; это словарь самой страницы, а не догадка:

| `pos` | Подпись в интерфейсе |
|---|---|
| `full_text` | Везде (умолчание) |
| `position` | В названии резюме |
| **`education`** | **В образовании** — вуз, факультет, специальность |
| `workplaces` | В опыте работы |
| `keywords` | В ключевых навыках |
| `previous_workplace` | в последнем месте работы |
| `workplace_organization` | В компаниях и отраслях |
| `workplace_position` | В должностях |
| `workplace_description` | В обязанностях |

`logic`: `normal` (все слова), `any` (любое из слов), `phrase` (точная фраза),
`except` (не встречаются).

### Что это даёт образованию

`pos=education` ищет по всей образовательной секции резюме — названию вуза, факультета
и специальности. Это единственный способ отобрать факультет **на сервере**: отдельного
структурного фильтра для факультета и специальности в `criteria` нет, там есть только
`education`, `education_level` и `university`.

Рабочая схема — структурный `university` для вуза плюс текст для факультета:

```
university=<id_вуза>&text=механико-математический&pos=education&logic=normal
&exp_period=all_time&relocation=living&search_period=365
```

Вуз задавать именно id (`resolveIds('university', 'МГУ')`), а не текстом: id — точное
соответствие, текст соберёт и однофамильцев вроде филиалов и созвучных названий.

Факультет в резюме — свободный текст с разнобойным написанием (`strategy.md`), поэтому
одна формулировка не покрывает факультет целиком. `logic=phrase` строже и уже, чем
`normal`, — совпадений чуть меньше. Семейство формулировок собирается несколькими
прогонами и склеивается по `hash` — так же, как семейство навыков.

**Оставшийся повод вскрывать карточки — год выпуска.** Он в текст не попадает, и
`pos=education` его не отбирает.

`search_field=education` принимается отдельным ключом `criteria.search_field`, но без
парных `pos`/`logic` выбрасывает сам `text` (в эхе `text: []`). Рабочая форма — `pos`,
не `search_field`.

**Следствие:** после каждого текстового запроса обязателен L1 — снять `text` и
убедиться, что `totalResults` изменился. Забытый `exp_period` не выглядит ошибкой:
запрос отработает, эхо покажет текст, числа опишут весь пул.

## Навыки

| Запрос | totalResults |
|---|---|
| база (разработчик, Москва) | 134 710 |
| `skill=1114` (Python) | 51 242 |
| `skill=1114&skill=845` (Python + MS Excel) | 2 950 |

Несколько `skill` — **пересечение (И)**, не объединение. Для «любой из навыков»
считать запросы по отдельности и объединять по `hash` (см. `strategy.md`).

`verified_skills` — отдельное поле для навыков, подтверждённых тестами hh. Своя шкала
id, покрытие много меньше: 70 позиций в фасете против 50 самых частых в `skill`.
Комбинирование `verified_skills` (И или ИЛИ) не тестировалось.

## Образование

| Запрос | totalResults |
|---|---|
| `education_level=higher` | 57 463 |
| `education_level=master` | 15 844 |
| `education_level=higher&education_level=master` | 73 145 |
| `education=higher` | **93 374** |

`education_level` — перечисление точных уровней, объединяемых через **ИЛИ**:
57 463 + 15 844 = 73 307 против фактических 73 145; разница 162 — люди с обоими
уровнями. Никакого «и выше» здесь нет: для «высшего и выше» перечислять `higher`,
`bachelor`, `master`, `candidate`, `doctor`.

`education` — другой, одиночный параметр (по умолчанию `none`), даёт заметно больший
охват. Точная семантика не выяснена; **для воспроизводимых отчётов использовать
`education_level`** и перечислять уровни явно.

## Регион и relocation

По умолчанию `relocation=living_or_relocation`: в регион попадают и те, кто там **не
живёт**, но готов переехать.

Новосибирск (`area=4`), разработчик, 365 дней:

| `relocation` | totalResults |
|---|---|
| `living` — живут в городе | 9 003 |
| `living_or_relocation` — **по умолчанию** | 11 307 |
| `relocation` — только готовые переехать | 2 204 |

Умолчание завышает региональный пул на **~26%**. Для зарплатного анализа конкретного
города почти всегда нужен `relocation=living`, иначе медиана смешивает местный рынок
с ожиданиями иногородних. `buildUrl` требует задавать `relocation` явно.

Иерархия ведёт себя ожидаемо, если убрать шум переезда: область (`area=1202`,
`living`) = 9 456 против города (`area=4`, `living`) = 9 003 — область включает город.

Значения: 1 = Москва, 2 = Санкт-Петербург, 113 = Россия, 2019 = Московская область.
Остальные — из справочника.

## Остальные фильтры

| Параметр | Значения |
|---|---|
| `professional_role` | id профроли, повторяемый (194 роли) |
| `experience` | `noExperience`, `between1And3`, `between3And6`, `moreThan6` |
| `salary_from`, `salary_to` | число в валюте `currency_code` |
| `currency_code` | `RUR`, `EUR`, `USD` |
| `age_from`, `age_to` | число |
| `gender` | `unknown`, `male`, `female` |
| `employment` | легаси, см. «Занятость и формат работы»: `full`, `part`, `project`, `volunteer`, `probation` |
| `employment_form` | `FULL`, `PART_TIME`, `INTERNSHIP`, `VOLUNTEER` |
| `schedule` | легаси, см. «Занятость и формат работы»: `fullDay`, `shift`, `flexible`, `remote`, `flyInFlyOut` |
| `work_format` | `ON_SITE`, `REMOTE`, `HYBRID`, `FIELD_WORK`, `FLY_IN_FLY_OUT` |
| `job_search_status` | `active_search`, `looking_for_offers`, `has_job_offer`, `accepted_job_offer`, `not_looking_for_job`, `unknown` |
| `business_trip_readiness` | `never`, `ready`, `sometimes` |
| `language` | код языка + уровень `a1`…`c2`, `l1` |
| `citizenship`, `work_ticket` | id страны |
| `university` | id вуза, объединяется по **ИЛИ** |
| `district`, `metro` | id района / ветки |
| `driver_license_types` | `A`, `B`, `C`, `D`, `E`, `BE`, `CE`, `DE`, `TM`, `TB` |
| `label` | `only_with_photo`, `only_with_salary`, `only_with_age`, `only_with_gender`, `only_with_vehicle`, `only_in_responses`, `exclude_viewed_by_user_id`, `exclude_viewed_by_employer_id` |

### Занятость и формат работы

Словари различаются между резюме и вакансиями:

| Параметр | `/search/resume` | `/search/vacancy` |
|---|---|---|
| `employment_form` | `FULL`, `PART_TIME`, `INTERNSHIP`, `VOLUNTEER` | `FULL`, `PART`, `PROJECT`, `FLY_IN_FLY_OUT` |
| `work_format` | `ON_SITE`, `REMOTE`, `HYBRID`, `FIELD_WORK`, `FLY_IN_FLY_OUT` | то же без `FLY_IN_FLY_OUT` |
| `working_hours` | не существует | `HOURS_2`…`HOURS_12`, `HOURS_24`, `FLEXIBLE`, `OTHER` |
| `work_schedule_by_days` | не существует | `SIX_ON_ONE_OFF`, `FIVE_ON_TWO_OFF`, `FOUR_ON_THREE_OFF`, `FOUR_ON_TWO_OFF`, `FOUR_ON_FOUR_OFF`, `THREE_ON_THREE_OFF`, `THREE_ON_TWO_OFF`, `TWO_ON_TWO_OFF`, `TWO_ON_ONE_OFF`, `ONE_ON_THREE_OFF`, `ONE_ON_TWO_OFF`, `WEEKEND`, `FLEXIBLE`, `OTHER` |

На `/search/resume` параметры `working_hours` и `work_schedule_by_days` отбрасываются
целиком и не попадают даже в эхо `criteria`.

Трансляция легаси-параметров (∅ — значение теряется, фильтр не работает):

```
employment: full→FULL · part→PART_TIME · project→PART_TIME
            volunteer→VOLUNTEER · probation→INTERNSHIP
schedule:   fullDay→[FIELD_WORK,ON_SITE,HYBRID] · remote→REMOTE
            flyInFlyOut→FLY_IN_FLY_OUT · shift→∅ · flexible→∅
```

Сам легаси-параметр в эхе `criteria` всегда пуст — заполняется поле, в которое он
транслирован. «Сменный» и «гибкий» график в данных размечены (фасет `schedule` отдаёт
по ним ненулевые числа), но применить их как фильтр нельзя, и в текущем интерфейсе hh
таких значений уже нет.

## Управление выдачей

| Параметр | Значения | Замечание |
|---|---|---|
| `items_on_page` | до **100** | Подтверждено. Всегда 100 |
| `page` | 0-based, максимум **49** | Страница 50 → 404 |
| `order_by` | `relevance`, `publication_time`, `salary_desc`, `salary_asc` | `relevance` не случаен — первые страницы смещены |
| `search_period` | `0`, `1`, `3`, `7`, `30`, `365` | Дней с обновления резюме. **По умолчанию 30** |
| `date_from`, `date_to` | дата | Альтернатива `search_period` |

`search_period` влияет на медиану сильнее большинства фильтров: 30 дней — «живые»
соискатели, 365 — весь пул с протухшими ожиданиями. `buildUrl` требует задавать явно.

## Справочники ID

Публичный API, **без авторизации**, CORS разрешён — работает прямо со страницы hh.ru
(`__hh.resolveIds`):

| Что | Эндпоинт |
|---|---|
| Навыки → id для `skill` | `https://api.hh.ru/suggests/skill_set?text=Python` → `{id: "1114", text: "Python"}` |
| Регионы → id для `area` | `https://api.hh.ru/suggests/areas?text=Новосибирск` → id + цепочка `parent` |
| Дерево регионов | `https://api.hh.ru/areas/113` — 88 регионов РФ |
| Вузы → id для `university` | `https://api.hh.ru/suggests/educational_institutions?text=МГУ` |
| Профроли → id | `https://api.hh.ru/suggests/professional_roles?text=разработчик` → `{id: "96"}` |

ID из `suggests` совпадают с ID фильтров сайта — проверено: Python = 1114 и в
`suggests`, и в фасете, и в рабочем фильтре. Внутренние `/autocomplete/*` на hh.ru —
404, не существуют.

**Подсказки ищут по префиксу и пропускают почти всё.** «Хранилища данных», «Витрины
данных», «Data Warehouse», «Data Mart», «Data Vault», «Data Engineering» дают пустой
ответ. Для сбора синонимов использовать фасет `skill`, а не `suggests` (см.
`strategy.md`).

Локальная копия enum-справочников, дерева 194 профролей и курсов валют:
`references/dictionaries.json`.

## Потолок 5000 и нарезка

`criteria.max_search_result = 5000`. При `items_on_page=100` доступны страницы 0–49;
страница 50 → **404** (`state.errorCode = 404`).

Обход — нарезка по зарплатным диапазонам, каждый срез получает свои 5000. Пример
(разработчик, Москва):

| Срез | totalResults |
|---|---|
| 0–100 000 | 20 088 |
| 100 000–200 000 | 18 113 |
| 200 000–1 000 000 | 19 035 |

Алгоритм (`sliceBySalary`): при `totalResults > 5000` рекурсивно делить диапазон
пополам. Дедуплицировать по `hash` — включительность границ не проверена, двойной
учёт на стыках вероятен.

**Следствие, которое легко упустить** (вывод из данных, не проверено напрямую): сумма
срезов 57 236 против базы 134 710 — то есть `salary_from`/`salary_to` отбирают только
резюме с **указанной** зарплатой. Объединение срезов равно зарплатной когорте, а не
исходной популяции. Долю «молчунов» после нарезки брать из `overview` без срезов.

### Два счётчика

```
stats.totalResults           // сгруппированные, дедуп по человеку
stats.totalUngroupedResults  // все резюме, включая несколько от одного соискателя
```

Пример: 11 416 против 12 917. Для аналитики — **`totalResults`**.

Счётчик фасета считается по недедуплицированному пулу: он сходится с
`totalUngroupedResults` того же фильтра с точностью до единиц записей (дрейф живых
данных между запросами), а `totalResults` прямого фильтрованного запроса ниже его на
величину порядка отношения `totalUngroupedResults/totalResults` для этой базы —
на восьми значениях `work_format` и `employment_form` это 11–17%. Сверять facet count
нужно с `totalUngroupedResults`; расхождение с `totalResults` не является признаком
сломанного фильтра.

## Фасеты

`state.searchClusters` — готовые распределения по текущему запросу, без обхода
страниц. `groups` это объект, не массив: `Object.values(cluster.groups)`.

Базовый обзор рынка — **один HTTP-запрос**. Доступны: `salary`, `age`, `experience`,
`education_level`, `job_search_status`, `work_format`, `schedule`, `employment`,
`employment_form`, `area`, `district` (125), `metro` (470), `professional_role` (194),
`skill` (топ-50), `verified_skills` (70), `language` (104), `gender`,
`business_trip_readiness`, `driver_license_types`, `citizenship`, `university`,
`work_ticket`, `relocation`, `label`.

Фасет `skill` вдвойне ценен: даёт топ востребованных компетенций внутри выборки **и**
готовые id для уточняющих запросов.

Зарплатный фасет — гистограмма с **адаптивными** границами: hh пересчитывает бакеты
под запрос. Между разными запросами бакеты несопоставимы; для сравнения задавать
одинаковые `salary_from`/`salary_to` вручную или считать перцентили по выборке.

`title` у бакетов `salary` и `age` пуст — подпись строить из `id` (`facets` это
делает). В ряде фасетов в `title` встречается `&nbsp;` — очищается там же.

## Схема записи резюме

`state.resumeSearchResult.resumes[]`, ~40 полей. Почти все скаляры завёрнуты в
**массив из одного элемента** — это разбирает `parseRow`.

| Поле | Форма | Смысл |
|---|---|---|
| `_attributes.hash` | строка | Ключ дедупликации |
| `_attributes.permission` | `view_without_contacts` | Уровень доступа |
| `_attributes.updated` | ms epoch | Свежесть |
| `title` | `[{string}]` | Желаемая должность |
| `salary` | `[{amount, currency}]` | **Заявлено соискателем.** Есть примерно у 19–41% |
| `predictedSalary` | `[{amount, currency}]` | **Оценка hh.** Другая шкала, см. `salary.md` |
| `totalExperience` | `[{string: <месяцы>}]` | Стаж в месяцах, число |
| `professionExperience` | `[{professionId, professionName, totalExperienceInMonths, experience[]}]` | Нормализованная профессия и стаж в ней |
| `shortExperience` | массив | `startDate`, `endDate`, `companyName`, `position`, `companyAreaId` |
| `keySkills` | `[{string}]` | Навыки |
| `area` | `[{string: <id>, trl: <название>}]` | Регион |
| `age` | `[{string}]` | Пустой массив, если скрыт |
| `gender` | `[{string}]` | |
| `jobSearchStatus` | `[{jobSearchStatus: {name, lastChangeTime}}]` | **Двойная вложенность** — частая ошибка парсинга |
| `liveness` | `[{isActive, score}]` | Оценка активности 0..1, недокументирована |
| `hiddenFields` | массив | Что соискатель скрыл |
| `canOpenContacts` | bool | Кнопка не скрыта. **Не значит «бесплатно»** — флаг игнорировать |

Образования в выдаче **нет**, но распределение по образованию берётся из фасета
`education_level` — открывать карточки для этого не нужно.

`professionExperience.professionId` — отдельный справочник профессий, не совпадающий
с `professional_role`; источник не найден.

### Карточка `/resume/<hash>`

Открывается (200), `state.resume` содержит ~100 полей: полный опыт, образование,
языки, сертификаты, портфолио. Контактные поля присутствуют ключами, но пусты без
оплаты. Обычный `GET`, денег не стоит, но расходует суточную квоту в 500 просмотров —
см. `protocol.md`.

**Для рыночного анализа не нужна** — выдача и фасеты покрывают задачу. Единственное
исключение — образование (факультет, год выпуска, специальность), см. `strategy.md`.

## Сторона спроса: вакансии

`/search/vacancy?…`, состояние в `state.vacancySearchResult`, `items_on_page=100`
работает (`vacancyOverview`).

```json
"compensation": {"from": 450000, "currencyCode": "RUR", "gross": false, "perModeFrom": 450000, "mode": "MONTH"}
```

Критично: `gross` (до/после НДФЛ) и `mode` (период). **Без нормализации сравнивать с
ожиданиями нельзя** — в резюме обычно указывают «на руки». Приводить к одному периоду
и одной базе, оговорку выносить в отчёт.

Свои фасеты: `compensation_mode`, `compensation_frequency`, `industry`, `subIndustry`,
`working_hours`, `work_schedule_by_days`, `experience`, `professional_role`,
`education`. Полезные поля: `responsesCount`, `totalResponsesCount` (конкуренция),
`publicationTime`, `workExperience`, `professionalRoleIds`.

## Что недоступно

| Раздел | Статус |
|---|---|
| Полнотекстовый поиск по резюме | Работает при `pos` + `logic` + `exp_period`; без `exp_period` принимается и не фильтрует |
| Контакты соискателей | `DENIED_NO_FA`, платно. Для анализа не нужны |
| `/employer/salary_review`, `/salary_review` | **404**, хотя флаг `salaryReview` в `userFeatures` есть |
| `/employer/analytics`, `/analytics` | 404 / 204 |
| `/employer/statistics` | 200, но **без** `HH-Lux-InitialState`; статистика по своим вакансиям, не по рынку |
| `api.hh.ru` для резюме | Нужен employer-токен и оплаченный доступ. Справочники открыты |
| AI-поиск (`prompt_text`) | `isExpEnabled: false` |

Доступны: `/employer/resumefolders` (избранное), `/resumesavedsearch` (автопоиск —
позволяет отслеживать динамику пула во времени).
