# Faz 1 — Plan teknik ak verifikasyon founisè

> Mizajou: aplikasyon an konstwi kounye a. Gade PROGRESS.md ak PROVIDER_RESEARCH.md pou estati aktyèl; tèks anba a konsève premye analiz la.

Dat referans: 23 oktòb 2026 (lè kliyan an). Estati: pwovizwa, verifikasyon ekstèn bloke.

## Prèv ak limit

Depo a te vid. Aksè Git read-only reyisi, san okenn branch/tag sou origin.
Kle Gemini/Google ak Expo, DATABASE_URL ak REDIS_URL pa prezan nan runtime.
Tout demann dokiman ki nan lis sous anba a te resevwa `Tunnel connection failed: 403 Forbidden`.
Sa pwouve yon restriksyon rezo; li pa pwouve sèvis la pa disponib nan peyi itilizatè a.
Domèn nesesè yo sove nan draft anviwònman an. Draft pa aplike oswa pibliye tèt li.
Pa gen pri, kota, vèsyon SDK, lisans oswa non modèl aktyèl ki verifye nan sesyon sa a.

## Chwa achitekti

Monorepo TypeScript/Python; yon backend modilè anvan mikwosèvis:

- Web: Next.js App Router, React, TypeScript, Tailwind.
- Mobil: Expo/React Native, TypeScript, Expo Router; menm API ak web la.
- API: FastAPI, Pydantic, SQLAlchemy ak Alembic; OpenAPI jenere kliyan TypeScript la.
- PostgreSQL: sous verite pou kont, pwojè, travay, kredi ak tranzaksyon.
- Redis + Celery: travay background; worker AI ak worker FFmpeg separe dapre resous.
- Object storage konpatib S3 prive; upload/download ak URL siyen kout dire.
- Yon sèvis idantite OIDC jere modpas, rekiperasyon ak Google/Apple; seleksyon sèvis la
  ap tann evalyasyon pri, rejyon, ekspòtasyon done ak kontra sou tretman done.
- OpenTelemetry pou tras/metrik; log estriktire san kle, prompt prive oswa URL siyen.

API ak worker CPU kapab kòmanse sou menm sèvis ekonomik; storage ak PostgreSQL
jere separeman. Pa rezève GPU 24/7 anvan mezi trafik/kout pou imaj gratis.
Pa chwazi vèsyon depandans san verifye matrix konpatibilite Expo/React Native,
Next/React/Node ak Python/FastAPI. Faz aplikasyon an dwe pin vèsyon ak lockfiles,
enstale an mòd frozen, epi teste build web/mobil ak API ansanm.

```text
apps/web/                 Next.js
apps/mobile/              Expo Router
services/api/             FastAPI ak migrasyon Alembic
services/worker/          Celery, adapters AI, FFmpeg/ffprobe
packages/api-client/      Jenere apati OpenAPI
packages/contracts/       Schema pataje ak kapasite founisè
packages/i18n/            en, pt-BR, fr, ht, es, ar, zh-Hans, id, sw
infra/                    Compose dev, deplwaman, backup
scripts/                  Verifikasyon ak antretyen
tests/                    Kontra, entegrasyon, sekirite, E2E
```

Estrikti aplikasyon sa a se yon plan; dosye sèvis yo poko aplike.

## Matris founisè — desizyon kondisyonèl

| Fonksyon | Kandida / desizyon | Gratis oswa peye | Pòt verifikasyon |
|---|---|---|---|
| Tèks/script/lyrics | Gemini, ID soti nan katalòg kont lan | Nivo gratis posib selon modèl/kont; pa konfime | modèl, quota, pri, rejyon, tèm done |
| Imaj debaz | Worker open-weight; FLUX.1-schnell kòm kandida pou evalye | Gratis pou itilizatè; GPU/storage peye pa Haytile | lisans aktyèl, VRAM, kalite, filtraj, benchmark |
| Imaj avanse/edit | Modèl Google ki ekspoze kapasite sa a | Bidjè peye oswa kota selon modèl | edit/reference/aspect/resolution teste separeman |
| Videyo | Sèvis Google si kont lan sipòte jenerasyon videyo | Planifye kòm peye; pri aktyèl poko verifye | dire klip, son, rezolisyon, referans, rejyon |
| Mizik enstrimantal | Evalye sèvis Google music API si ofisyèlman disponib | Pa konfime | API piblik, kont, lisans, longè |
| Chante ak vokal | Founisè chante espesyalize; poko chwazi | Prevwa peye, san estimasyon envante | API ofisyèl, dwa komèsyal, lyrics egzak, senk lang |
| Vwa | Google TTS si modèl API kont lan sipòte sa | Pa konfime | vwa/lang, PCM/codec, pri, konsantman |
| MiniDrama | Orkestrasyon tèks + imaj + videyo + vwa + lip-sync | Sòm depans sèvis yo | pa gen yon sèl modèl ki sipoze fè tout workflow la |

Pa itilize TTS kòm chante. Pa sèvi ak yon API ki pa ofisyèl pou kontoune yon sèvis mizik.
Pa aktive yon altènativ ki chanje lyrics, lang, pri oswa lisans san konsantman.
Yon fonksyon ki pa verifye parèt dezaktive ak eksplikasyon; pa montre fo rezilta.

## Kontra provider

Registry admin an estoke ID provider/modèl, dat verifikasyon, sous pri ak lisans,
modalite antre/sòti, lang teste, dire/rezolisyon sipòte, rejyon, limit, estati.
Adapter bay discover, validate_input, estimate, submit, poll, cancel si sipòte,
fetch_result ak normalize_error. Kapasite soti nan metadata **ak** tès reyèl;
`list models` pou kont li pa prèv yon modèl ka fè chante oswa videyo.

Snapshot modèl/pri/paramèt rete sou chak travay. Timeout oswa 429 itilize retry
ak backoff/jitter; auth/unsupported pa retry san chanjman. Fallback bezwen kapasite
konpatib, limit pri ak otorizasyon itilizatè; pa itilize modèl pi chè an silans.
Yon timeout apre submit antre nan rekonsilyasyon anvan nenpòt lòt submit.

## Videyo 8–180 segonn ak MiniDrama

Planifikatè a konstwi sèn dapre dire natif modèl ki verifye a. Li konsève script,
character IDs, referans, rad, vwa, kote, continuity notes, paramèt ak lòd sèn.
Li pa sipoze chak modèl bay menm dire klip. Itilizatè apwouve nenpòt chanjman tèks.
Worker yo jenere sèn endepandan, verifye fichye ak ffprobe, valide rezolisyon,
FPS ak odyo, epi monte avèk FFmpeg. Yo ka retire depase nan fwontyè sèn; pa ralanti
klip pou ranpli dire ki manke. Sous, klip ak montaj final rete vèsyone.

Quality check mezire dekodaj, dire nan tolerans kontra a, odyo prezan lè obligatwa,
rezolisyon, clipping/silans, timestamps soutit ak lòd sèn. ASR/vision kapab bay
avètisman sou lyrics, bouch ak kontinwite, men pa garanti deteksyon tout erè.
Rejenerasyon yon sèn kreye nouvo revision epi remonte sèlman rezilta ki depann de li.
`completed` mande fichye final valide nan storage; apwobasyon itilizatè se yon lòt chan.

## Plan depans

Pa gen montan fiks pwopoze san sous aktyèl. Ledger pri a bezwen lajan, inite,
pri/inite, dat validite, sous, rejyon ak règleman taks. Kalkil entèn:

`depans = API + GPU tan × tarif + storage + egress + worker + moderasyon + retry`

Videyo konte klip ak son/rezolisyon; tèks konte in/out tokens selon founisè;
od yo konte dire oswa token selon tarif reyèl la. Mete quote ekspire ak limit maksimòm,
konfimasyon eksplisit, rezèvasyon atomik ak rekonsilyasyon apre rezilta.
Kredi pa yon lajan fiks jiskaske admin defini konvèsyon ak maj.

Imaj debaz: **zewo debi kredi**, menm sou retry. Limit pa kont/IP, concurrency,
rezolisyon/dire GPU, bidjè chak jou ak kill switch. Lè bidjè fini, mete queue/mesaj
kapasite; pa chaje otomatikman. Nivo gratis founisè pa pwomès sèvis san limit.
Benchmark detèmine kantite imaj gratis anvan lansman. Pa envante limit ekonomik.

## OTA ak CI/CD

Development, staging ak production separe; EAS Build/EAS Update pou mobil.
Sèvi ak runtimeVersion dapre fingerprint si SDK chwazi a sipòte politik sa a.
Chanjman natif, pèmisyon oswa SDK mande nouvo build; OTA pou chanjman konpatib sèlman.
CI: lint/typecheck → unit/integration → build → E2E → staging → apwobasyon production.
Tokens EAS ak kle signing rete nan secrets CI. Branch pwoteje ak revizyon obligatwa.
OTA rollout piti an premye si sèvis aktyèl la sipòte sa, metrik erè, rollback teste.
Yon update ki gen nouvo schema lokal dwe sipòte rollback. API kenbe konpatibilite
ak kliyan ki poko mete ajou; migrasyon expand/backfill/contract.
Web deplwaye sou merge apre tès; backend deplwaye endepandamman avèk healthcheck
ak rollback. Pa gen workflow deplwaman aktif ni build AAB/IPA nan Faz 1.

## Sous ofisyèl pou reverifye

Tout URL sa yo te eseye men bloke nan sesyon sa a; yo pa sous ki te li avèk siksè:

- https://ai.google.dev/gemini-api/docs/models
- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/rate-limits
- https://ai.google.dev/gemini-api/docs/available-regions
- https://ai.google.dev/gemini-api/terms
- https://ai.google.dev/gemini-api/docs/image-generation
- https://ai.google.dev/gemini-api/docs/video
- https://ai.google.dev/gemini-api/docs/music-generation
- https://ai.google.dev/gemini-api/docs/speech-generation
- https://docs.expo.dev/eas-update/introduction/
- https://docs.expo.dev/eas-update/runtime-versions/
- https://huggingface.co/black-forest-labs/FLUX.1-schnell/raw/main/README.md

Apre aksè: dokimante dat/sous, modèl egzak, billing tier, kota pwojè,
restriksyon rejyon/lisans, pri ak konsantman anvan yon tès ki koute lajan.
