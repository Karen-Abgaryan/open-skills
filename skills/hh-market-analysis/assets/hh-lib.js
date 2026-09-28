/* hh-lib.js — collection library for hh.ru resume/vacancy market analysis.
 *
 * Inject once per browser session by pasting the whole file as the body of a
 * browser_evaluate arrow function. Defines window.__hh. Re-inject after any
 * navigation — page reload wipes it.
 *
 * Read-only by construction: assertSafe() is called before every request and
 * rejects anything outside the GET whitelist. There is no code path here that
 * can spend money.
 */
(() => {
  'use strict';

  const VERSION = '1.2.1';

  // ---------------------------------------------------------------- safety --

  // Only these hh.ru paths may be requested. Everything else throws.
  const ALLOWED_HH_PATHS = [
    /^\/search\/resume$/,
    /^\/search\/vacancy$/,
    /^\/resume\/[A-Za-z0-9]+$/,
  ];

  // Paid / mutating surfaces. Matched against the path and against parameter
  // NAMES — never against parameter values: with text search working, a resume
  // query legitimately contains words like "order", "contact" or "price".
  const FORBIDDEN = /(negotiation|contact|buy|price|cart|purchase|pfp|topic|invite|payment|billing|order)/i;

  // Read-only parameter names that collide with FORBIDDEN as substrings.
  // order_by is ordinary result ordering and has nothing to do with purchases.
  const SAFE_PARAM_NAMES = new Set(['order_by']);

  // Public reference API — no auth, CORS-enabled, costs nothing.
  const ALLOWED_API = /^https:\/\/api\.hh\.ru\/(areas|suggests)(\/|$)/;

  function assertSafe(url) {
    let u;
    try {
      u = new URL(url, 'https://hh.ru');
    } catch (e) {
      throw new Error(`assertSafe: unparseable URL: ${url}`);
    }
    if (u.protocol !== 'https:') throw new Error(`assertSafe: non-https: ${url}`);
    if (FORBIDDEN.test(u.pathname)) {
      throw new Error(`assertSafe: forbidden pattern in path: ${u.pathname}`);
    }
    for (const name of u.searchParams.keys()) {
      if (!SAFE_PARAM_NAMES.has(name) && FORBIDDEN.test(name)) {
        throw new Error(`assertSafe: forbidden pattern in parameter name: ${name}`);
      }
    }

    if (u.hostname === 'api.hh.ru') {
      if (!ALLOWED_API.test(u.href)) throw new Error(`assertSafe: api.hh.ru path not whitelisted: ${url}`);
      return u.href;
    }
    if (u.hostname !== 'hh.ru' && u.hostname !== 'www.hh.ru') {
      throw new Error(`assertSafe: host not whitelisted: ${u.hostname}`);
    }
    if (!ALLOWED_HH_PATHS.some(re => re.test(u.pathname))) {
      throw new Error(`assertSafe: path not whitelisted: ${u.pathname}`);
    }
    return u.href;
  }

  // --------------------------------------------------------------- fetching --

  const sleep = ms => new Promise(r => setTimeout(r, ms));

  // Random, never fixed: an even interval is itself a robot signal.
  const humanDelay = () => {
    const base = 1500 + Math.random() * 3500;                              // 1.5–5.0 s
    const distracted = Math.random() < 0.12 ? 4000 + Math.random() * 8000 : 0;
    return base + distracted;
  };

  class HardStop extends Error {}

  // <template> content lives in a DocumentFragment, so textContent is empty.
  // innerHTML is the only thing that works here.
  const parseState = html => {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const el = doc.querySelector('#HH-Lux-InitialState');
    if (!el) return null;
    return JSON.parse(el.innerHTML);
  };

  async function fetchState(url) {
    const safe = assertSafe(url);
    const r = await fetch(safe, { method: 'GET', credentials: 'include' });
    if (r.status === 429 || r.status === 403) {
      throw new HardStop(`HTTP ${r.status} on ${safe} — stop, do not retry, report to the operator`);
    }
    if (r.redirected && /captcha/i.test(r.url)) {
      throw new HardStop(`captcha redirect: ${r.url} — stop, do not retry, report to the operator`);
    }
    const html = await r.text();
    const state = parseState(html);
    if (!state) throw new Error(`no HH-Lux-InitialState in response for ${safe} (HTTP ${r.status})`);
    if (state.errorCode) throw new Error(`hh returned errorCode ${state.errorCode} for ${safe}`);
    return state;
  }

  async function fetchJson(url) {
    const safe = assertSafe(url);
    const r = await fetch(safe, { method: 'GET' });
    if (r.status === 429 || r.status === 403) {
      throw new HardStop(`HTTP ${r.status} on ${safe} — stop, do not retry, report to the operator`);
    }
    return r.json();
  }

  // ------------------------------------------------------------------- auth --

  function checkAuth() {
    const el = document.querySelector('#HH-Lux-InitialState');
    if (!el) return { authed: false, reason: 'no state on current page' };
    const s = JSON.parse(el.innerHTML);
    return {
      authed: !!s.employerId,
      employerId: s.employerId || null,
      canSearchResumes: (s.userFeatures || []).includes('resumeSearch'),
    };
  }

  // ------------------------------------------------------------ url building --

  // AI search is switched off for this account (isExpEnabled: false).
  const BANNED_PARAMS = ['prompt_text'];

  // Text search filters, but only when exp_period rides along with it: without
  // that companion the query is accepted, echoes back in criteria.text, and
  // returns the untouched pool. The hh interface always sends exp_period, so the
  // trap only springs on hand-built URLs — and it springs silently. pos and
  // logic are required too: without them text is not even parsed.
  const TEXT_COMPANIONS = ['pos', 'logic', 'exp_period'];

  const POS_VALUES = new Set([
    'full_text',              // Везде
    'position',               // В названии резюме
    'education',              // В образовании — вуз, факультет, специальность
    'workplaces',             // В опыте работы
    'keywords',               // В ключевых навыках
    'previous_workplace',     // в последнем месте работы
    'workplace_organization', // В компаниях и отраслях
    'workplace_position',     // В должностях
    'workplace_description',  // В обязанностях
  ]);
  const LOGIC_VALUES = new Set(['normal', 'any', 'phrase', 'except']);
  const EXP_PERIOD_VALUES = new Set(['all_time', 'last_year', 'last_three_years',
                                     'last_six_years']);

  // Defaults that materially change results and must therefore be stated, not
  // inherited: relocation defaults to living_or_relocation (inflates a region by
  // ~26%), search_period defaults to 30 days.
  const REQUIRED_PARAMS = ['relocation', 'search_period'];

  // text/pos/logic travel as parallel slots: the i-th text is read with the i-th
  // pos and the i-th logic.
  const ARRAY_PARAMS = new Set([
    'text', 'pos', 'logic', 'exp_period', 'exp_company_size',
    'professional_role', 'skill', 'verified_skills', 'experience', 'education_level',
    'employment', 'employment_form', 'schedule', 'work_format', 'job_search_status',
    'label', 'language', 'citizenship', 'work_ticket', 'university', 'district',
    'metro', 'driver_license_types', 'area', 'business_trip_readiness',
  ]);

  function buildUrl(spec, path = '/search/resume') {
    const banned = BANNED_PARAMS.filter(p => spec[p] !== undefined);
    if (banned.length) {
      throw new Error(`buildUrl: banned parameter(s) ${banned.join(', ')} — not available on this account`);
    }
    if (spec.text !== undefined && spec.text !== null && spec.text !== '') {
      const orphaned = TEXT_COMPANIONS.filter(p => spec[p] === undefined || spec[p] === null);
      if (orphaned.length) {
        throw new Error(
          `buildUrl: text needs ${orphaned.join(', ')} — without exp_period the query is accepted, ` +
          `echoes back in criteria.text and returns the whole pool unfiltered; without pos and logic ` +
          `the text is not parsed at all. Send text + pos + logic + exp_period together, then confirm ` +
          `with L1 that totalResults actually moved.`
        );
      }
      const bad = [];
      for (const v of [].concat(spec.pos)) if (!POS_VALUES.has(v)) bad.push(`pos=${v}`);
      for (const v of [].concat(spec.logic)) if (!LOGIC_VALUES.has(v)) bad.push(`logic=${v}`);
      for (const v of [].concat(spec.exp_period)) if (!EXP_PERIOD_VALUES.has(v)) bad.push(`exp_period=${v}`);
      if (bad.length) {
        throw new Error(`buildUrl: unknown value(s) ${bad.join(', ')} — see references/filters.md for the enums`);
      }
    }
    const missing = REQUIRED_PARAMS.filter(p => spec[p] === undefined || spec[p] === null);
    if (missing.length) {
      throw new Error(
        `buildUrl: ${missing.join(', ')} must be set explicitly — hh defaults ` +
        `(relocation=living_or_relocation, search_period=30) change the answer silently.`
      );
    }

    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(spec)) {
      if (v === undefined || v === null || v === '') continue;
      if (Array.isArray(v)) {
        if (!ARRAY_PARAMS.has(k)) throw new Error(`buildUrl: ${k} is not a repeatable parameter`);
        v.forEach(x => qs.append(k, String(x)));
      } else {
        qs.append(k, String(v));
      }
    }
    if (!qs.has('items_on_page')) qs.set('items_on_page', '100');
    return `https://hh.ru${path}?${qs.toString()}`;
  }

  // ----------------------------------------------------- L0: criteria echo ---

  // The backend echoes its parse of the request into criteria. A parameter
  // missing from the echo was dropped outright. A parameter present in the echo
  // is NOT proven to filter — that is what L1 is for.
  function criteriaDiff(url, criteria) {
    const sent = new URL(url).searchParams;
    const dropped = [];
    const seen = new Set();
    for (const key of sent.keys()) {
      if (seen.has(key)) continue;
      seen.add(key);
      if (['items_on_page', 'page', 'order_by'].includes(key)) continue;
      const echoed = criteria ? criteria[key] : undefined;
      const present = Array.isArray(echoed) ? echoed.length > 0
        : (echoed !== undefined && echoed !== null && echoed !== '');
      if (!present) dropped.push({ param: key, sentValues: sent.getAll(key), echoed: echoed ?? null });
    }
    return dropped;
  }

  // ----------------------------------------------------------- facets/stats --

  const clean = s => (typeof s === 'string' ? s.replace(/&nbsp;/g, ' ').trim() : s);

  function facets(state) {
    const clusters = state.searchClusters || {};
    const out = {};
    for (const [name, cluster] of Object.entries(clusters)) {
      const groups = cluster && cluster.groups ? Object.values(cluster.groups) : [];
      if (!groups.length) continue;
      out[name] = groups.map(g => ({
        id: g.id,
        // salary and age buckets ship an empty title — fall back to the id.
        title: clean(g.title) || String(g.id),
        count: g.count,
      }));
    }
    return out;
  }

  const stats = state => ({
    totalResults: state?.resumeSearchResult?.stats?.totalResults ?? null,
    totalUngroupedResults: state?.resumeSearchResult?.stats?.totalUngroupedResults ?? null,
    maxSearchResult: state?.resumeSearchResult?.criteria?.max_search_result ?? null,
  });

  // Aggregates for the whole population in one request: totals, every facet, and
  // the L0 criteria check.
  async function overview(spec) {
    const url = buildUrl(spec);
    const state = await fetchState(url);
    const criteria = state?.resumeSearchResult?.criteria ?? null;
    return {
      url,
      ...stats(state),
      droppedParams: criteriaDiff(url, criteria),
      criteria,
      facets: facets(state),
    };
  }

  // ------------------------------------------- L1: does the filter do anything --

  // Drops one parameter at a time and re-counts. Equal totals mean the parameter
  // is being ignored — the failure mode that makes `text` useless.
  async function filterEfficacy(spec, params) {
    const base = await overview(spec);
    const results = [];
    for (const p of params) {
      await sleep(humanDelay());
      const reduced = { ...spec };
      delete reduced[p];
      let withoutTotal = null, error = null;
      try {
        withoutTotal = (await overview(reduced)).totalResults;
      } catch (e) {
        error = String(e.message || e);
        if (e instanceof HardStop) { results.push({ param: p, error }); break; }
      }
      results.push({
        param: p,
        value: spec[p],
        baseTotal: base.totalResults,
        withoutTotal,
        // A real filter must shrink the set. No change = silently ignored.
        effective: withoutTotal !== null ? withoutTotal > base.totalResults : null,
        error,
      });
    }
    return { baseUrl: base.url, baseTotal: base.totalResults, checks: results };
  }

  // ------------------------------------------------------------ row parsing --

  const val = f => (Array.isArray(f) && f.length
    ? (f[0] && f[0].string !== undefined ? f[0].string : f[0])
    : null);
  const money = f => (Array.isArray(f) && f.length && f[0]
    ? { amount: f[0].amount ?? null, currency: f[0].currency ?? null }
    : null);

  function parseRow(r) {
    const a = r._attributes || {};
    const areaEntry = Array.isArray(r.area) && r.area.length ? r.area[0] : null;
    const prof = Array.isArray(r.professionExperience) && r.professionExperience.length
      ? r.professionExperience[0] : null;
    const exp = Array.isArray(r.totalExperience) && r.totalExperience.length
      ? Number(val(r.totalExperience)) : null;
    return {
      hash: a.hash ?? null,
      url: a.hash ? `https://hh.ru/resume/${a.hash}` : null,
      permission: a.permission ?? null,
      updated: a.updated ?? null,
      title: clean(val(r.title)),
      salary: money(r.salary),                 // stated by the candidate
      predictedSalary: money(r.predictedSalary), // hh's estimate — different scale
      totalExperienceMonths: Number.isFinite(exp) ? exp : null,
      professionName: prof ? clean(prof.professionName) : null,
      professionId: prof ? prof.professionId : null,
      professionMonths: prof ? prof.totalExperienceInMonths : null,
      areaId: areaEntry ? (areaEntry.string ?? null) : null,
      areaName: areaEntry ? clean(areaEntry.trl ?? null) : null,
      age: val(r.age),
      gender: val(r.gender),
      // Double nesting here is a common parsing mistake.
      jobSearchStatus: r.jobSearchStatus?.[0]?.jobSearchStatus?.name ?? null,
      liveness: r.liveness?.[0]?.score ?? null,
      keySkills: Array.isArray(r.keySkills) ? r.keySkills.map(s => clean(val([s]))).filter(Boolean) : [],
      positions: Array.isArray(r.shortExperience)
        ? r.shortExperience.map(e => ({
            position: clean(e.position ?? null),
            company: clean(e.companyName ?? null),
            startDate: e.startDate ?? null,
            endDate: e.endDate ?? null,
            companyAreaId: e.companyAreaId ?? null,
          }))
        : [],
      hiddenFields: Array.isArray(r.hiddenFields) ? r.hiddenFields : [],
    };
  }

  // --------------------------------------------------------------- harvest ---

  const MAX_PAGE = 49;        // page 50 → 404
  const DEFAULT_PAGE_CAP = 20; // 2000 resumes; more only with operator consent

  // Collects pages with randomised pauses and dedups by hash. Returns rows plus
  // the metadata L2 integrity checks need.
  async function harvest(spec, maxPages = DEFAULT_PAGE_CAP, opts = {}) {
    const cap = Math.min(maxPages, MAX_PAGE + 1);
    const pages = opts.pages || null; // explicit page list, for random sampling
    const plan = pages
      ? pages.filter(p => p >= 0 && p <= MAX_PAGE).slice(0, cap)
      : Array.from({ length: cap }, (_, i) => i);

    const seen = new Map();
    const meta = {
      url: null, totalResults: null, totalUngroupedResults: null, maxSearchResult: null,
      pagesRequested: plan.length, pagesFetched: 0, pagesPlan: plan,
      rawRows: 0, duplicates: 0, droppedParams: [], stoppedReason: null,
      collectedAt: new Date().toISOString(), pageCap: cap, tag: opts.tag || null,
    };

    for (let i = 0; i < plan.length; i++) {
      const url = buildUrl({ ...spec, page: plan[i] });
      if (i === 0) meta.url = url;
      let state;
      try {
        state = await fetchState(url);
      } catch (e) {
        meta.stoppedReason = String(e.message || e);
        break;
      }
      if (i === 0) {
        Object.assign(meta, stats(state));
        meta.droppedParams = criteriaDiff(url, state?.resumeSearchResult?.criteria ?? null);
      }
      const batch = state?.resumeSearchResult?.resumes ?? [];
      meta.pagesFetched++;
      meta.rawRows += batch.length;
      for (const raw of batch) {
        const row = parseRow(raw);
        if (!row.hash) continue;
        if (seen.has(row.hash)) { meta.duplicates++; continue; }
        seen.set(row.hash, row);
      }
      if (!batch.length) { meta.stoppedReason = meta.stoppedReason || 'empty page'; break; }
      if (i < plan.length - 1) await sleep(humanDelay());
    }

    meta.uniqueRows = seen.size;
    // 5000 is the hard ceiling on any single query; beyond it the tail is
    // unreachable and percentiles describe only the reachable head.
    meta.capHit = meta.totalResults !== null && meta.totalResults > (meta.maxSearchResult || 5000);
    return { meta, rows: [...seen.values()] };
  }

  // ----------------------------------------------------------- card harvest --

  // hh caps an employer account at 500 resume VIEWS per day, reset at 00:00 MSK.
  // Search and facets are exempt; only /resume/<hash> counts. Past the cap the
  // card comes back as errorCode 409 instead of data — a quota, not a network
  // blip, so retries and longer pauses buy nothing. The counter lives here so
  // the limit is hit as a clean stop with a resumable queue rather than as a
  // string of failures the caller has to interpret.
  const DAILY_CARD_CAP = 500;

  const mskDay = (d = new Date()) =>
    new Date(d.getTime() + 3 * 3600 * 1000).toISOString().slice(0, 10);

  const cardQuota = { day: mskDay(), used: 0 };

  function cardQuotaLeft() {
    if (cardQuota.day !== mskDay()) { cardQuota.day = mskDay(); cardQuota.used = 0; }
    return DAILY_CARD_CAP - cardQuota.used;
  }

  // Education — faculty, speciality, graduation year — exists only on the card;
  // the search result has none of it. Everything else about a career track is
  // already in the listing, so opening cards is worth it for education alone.
  function parseCard(state, hash) {
    const edu = state?.resume?.primaryEducation?.value
      ?? state?.primaryEducation?.value
      ?? state?.resume?.primaryEducation
      ?? null;
    const list = Array.isArray(edu) ? edu : [];
    return {
      hash,
      educationLevel: state?.resume?.educationLevel?.value
        ?? state?.resume?.educationLevel ?? null,
      education: list.map(e => ({
        year: e.year ?? null,
        organization: clean(e.organization ?? null),  // faculty, free text
        result: clean(e.result ?? null),              // speciality, free text
        name: clean(e.name ?? null),                  // university
        universityId: e.universityId ?? null,
        specialtyId: e.specialtyId ?? null,           // ~37% filled, unreliable
        level: e.level ?? null,
      })),
    };
  }

  // Walks a list of hashes one at a time — never in parallel: two workers at
  // ~1 req/s drew a captcha after 31 cards, while a single thread at 1.5–5 s
  // passed 909 requests without one. Returns what it got plus the untouched
  // remainder, so the run resumes tomorrow instead of restarting.
  async function harvestCards(hashes, opts = {}) {
    const tags = opts.tags || {};                    // hash → caller's own label
    const cap = Math.min(opts.limit ?? DAILY_CARD_CAP, cardQuotaLeft());
    const queue = [...hashes];
    const results = [];
    const meta = {
      requested: hashes.length, ok: 0, failed: 0, errors: [],
      quotaUsedBefore: cardQuota.used, dailyCap: DAILY_CARD_CAP,
      startedAt: new Date().toISOString(), finishedAt: null,
      stoppedReason: null, remaining: [],
    };
    if (cap <= 0) {
      meta.stoppedReason = `daily cap of ${DAILY_CARD_CAP} card views already spent — resume after 00:00 MSK`;
      meta.remaining = queue;
      meta.finishedAt = new Date().toISOString();
      return { meta, cards: results };
    }

    while (queue.length && results.length + meta.failed < cap) {
      const hash = queue.shift();
      try {
        const state = await fetchState(`https://hh.ru/resume/${hash}`);
        cardQuota.used++;
        results.push({ tag: tags[hash] ?? opts.tag ?? null, ...parseCard(state, hash) });
        meta.ok++;
      } catch (e) {
        const msg = String(e.message || e);
        // 409 is the quota, not this card: stop and keep the hash in the queue.
        if (/errorCode 409/.test(msg)) {
          cardQuota.used = DAILY_CARD_CAP;
          queue.unshift(hash);
          meta.stoppedReason = `daily cap of ${DAILY_CARD_CAP} card views reached (errorCode 409) — ` +
            `resume after 00:00 MSK with the remaining hashes; retrying now cannot help`;
          break;
        }
        if (e instanceof HardStop) {
          queue.unshift(hash);
          meta.stoppedReason = msg;
          break;
        }
        meta.failed++;
        meta.errors.push({ hash, msg });
      }
      if (queue.length) await sleep(humanDelay());
    }

    meta.remaining = queue;
    meta.quotaUsedAfter = cardQuota.used;
    meta.quotaLeftToday = Math.max(0, DAILY_CARD_CAP - cardQuota.used);
    meta.stoppedReason = meta.stoppedReason
      || (queue.length ? `run limit of ${cap} reached` : null);
    meta.finishedAt = new Date().toISOString();
    return { meta, cards: results };
  }

  // Random page sampling — order_by=relevance is not random, so the first pages
  // are biased. Use when a sample, not a census, is enough.
  function randomPages(totalResults, nPages) {
    const available = Math.min(Math.ceil(totalResults / 100), MAX_PAGE + 1);
    const pool = Array.from({ length: available }, (_, i) => i);
    for (let i = pool.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [pool[i], pool[j]] = [pool[j], pool[i]];
    }
    return pool.slice(0, nPages).sort((a, b) => a - b);
  }

  // ------------------------------------------------------- salary slicing ----

  // Splits a query that exceeds max_search_result into salary bands, each with
  // its own 5000 ceiling. Note: salary_from/salary_to only match resumes where
  // the candidate stated a salary, so the union of slices is NOT the original
  // population — it is the stated-salary cohort only.
  async function sliceBySalary(spec, lo = 0, hi = 2000000, depth = 0, acc = []) {
    if (depth > 6) { acc.push({ lo, hi, total: null, note: 'depth limit' }); return acc; }
    const sliceSpec = { ...spec, salary_from: lo, salary_to: hi, currency_code: spec.currency_code || 'RUR' };
    const o = await overview(sliceSpec);
    if (o.totalResults !== null && o.totalResults > (o.maxSearchResult || 5000) && hi - lo > 5000) {
      const mid = Math.round((lo + hi) / 2);
      await sleep(humanDelay());
      await sliceBySalary(spec, lo, mid, depth + 1, acc);
      await sleep(humanDelay());
      await sliceBySalary(spec, mid, hi, depth + 1, acc);
    } else {
      acc.push({ lo, hi, total: o.totalResults, url: o.url });
    }
    return acc;
  }

  // ------------------------------------------------- spot-check for operator --

  // Random sample of resume links with the values this library parsed next to
  // them, so a human can open a few and confirm the parse matches the page.
  function spotCheck(rows, n = 10) {
    const pool = [...rows];
    for (let i = pool.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [pool[i], pool[j]] = [pool[j], pool[i]];
    }
    return pool.slice(0, n).map(r => ({
      url: r.url,
      title: r.title,
      salary: r.salary ? `${r.salary.amount} ${r.salary.currency}` : null,
      predictedSalary: r.predictedSalary ? `${r.predictedSalary.amount} ${r.predictedSalary.currency}` : null,
      areaName: r.areaName,
      totalExperienceMonths: r.totalExperienceMonths,
      currentPosition: r.positions[0]?.position ?? null,
      jobSearchStatus: r.jobSearchStatus,
    }));
  }

  // ------------------------------------------------------------ dictionaries --

  async function resolveIds(kind, text) {
    const kinds = {
      skill: 'skill_set',
      area: 'areas',
      university: 'educational_institutions',
      professional_role: 'professional_roles',
    };
    const endpoint = kinds[kind];
    if (!endpoint) throw new Error(`resolveIds: unknown kind ${kind} (use ${Object.keys(kinds).join(', ')})`);
    const data = await fetchJson(`https://api.hh.ru/suggests/${endpoint}?text=${encodeURIComponent(text)}`);
    return data.items || [];
  }

  // --------------------------------------------------------- vacancy side ----

  function parseVacancy(v) {
    const c = v.compensation || {};
    return {
      id: v.vacancyId ?? v.id ?? null,
      name: clean(v.name ?? null),
      from: c.from ?? null,
      to: c.to ?? null,
      currency: c.currencyCode ?? null,
      gross: c.gross ?? null,        // pre-tax flag — resumes are usually net
      mode: c.mode ?? null,          // MONTH / other period
      responsesCount: v.responsesCount ?? null,
      totalResponsesCount: v.totalResponsesCount ?? null,
      publicationTime: v.publicationTime?.timestamp ?? v.publicationTime ?? null,
      workExperience: v.workExperience ?? null,
      professionalRoleIds: v.professionalRoleIds ?? null,
      areaName: clean(v.area?.name ?? null),
    };
  }

  async function vacancyOverview(spec) {
    const url = buildUrl(spec, '/search/vacancy');
    const state = await fetchState(url);
    const res = state.vacancySearchResult || {};
    return {
      url,
      totalResults: res.totalResults ?? null,
      criteria: res.criteria ?? null,
      droppedParams: criteriaDiff(url, res.criteria ?? null),
      facets: facets(state),
      items: (res.vacancies || []).map(parseVacancy),
    };
  }

  window.__hh = {
    VERSION, assertSafe, buildUrl, checkAuth, fetchState, fetchJson,
    overview, facets, stats, criteriaDiff, filterEfficacy,
    harvest, randomPages, parseRow, sliceBySalary, spotCheck,
    harvestCards, parseCard, cardQuotaLeft, DAILY_CARD_CAP,
    resolveIds, vacancyOverview, humanDelay, sleep,
  };
  return { loaded: true, version: VERSION, api: Object.keys(window.__hh) };
})();
