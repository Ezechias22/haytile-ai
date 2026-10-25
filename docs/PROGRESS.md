# HAYTILE AI — estati livrezon

## Dènye chanjman: entèfas ak chaj Render

Etikèt vèsyon tès retire nan entèfas 9 lang yo. Disponibilite AI vin yon mesaj sèvis
nòmal, avèk backend ki refize demann AI pandan pa gen kredi API. Preview/download
prive sèvi lyen Firebase dirèk ki ekspire apre 5 minit, san gwo medya pase nan
Render. Kontè limit yo deplase sou Firestore (database ID `default`) avèk preconditions
atomik; kont/travay/kredi/pwojè yo poko migre. Polling inaktif retire.

Worker Render la ka pa demare ditou avèk switch operatè a; montaj lou an poz, pa
deklare li deplwaye sou Cloud Run. Kont sèvis aktyèl la manke otorizasyon deplwaman
compute yo. 62 tès backend, 3 workflow navigatè, build/TypeScript ak tès dirèk sou
Firebase/Firestore pase. Gade [detay offload la](FIREBASE_OFFLOAD.md).

Deploy fddb194 live sou menm sèvis Render gratis la. Tès piblik la konfime medya
Firebase dirèk, download prive/siyati/Range, izolasyon ant kont, kontè enskripsyon
ki rete sou Firestore, ak refi AI_SERVICE_PAUSED san kreye travay. Nouvo assets
entèfas yo pa gen ansyen etikèt vèsyon tès yo. Metadata kont/kredi yo toujou SQL
tanporè; yo pa deklare tout app la fini oswa Cloud Run worker deplwaye.

## Chwa Firebase, 25 oktòb 2026

Itilizatè a konfime Firebase pou medya; li kounye a kreye pwojè/app web la epi aktive
Storage ak Firestore. Credentials backend ak bucket la verifye; Firebase Storage
deplwaye sou Render Free avèk source a187b45. Adapter prive Firebase
Storage ajoute avèk credentials backend eksplisit, namespace haytile/, lekti pa
moso ak sipò download Range ki deja egziste. Worker la mete klip sèn yo nan dosye
travay tanporè epi netwaye yo, olye kenbe tout lis klip yo nan RAM. Firebase pa
ogmante RAM Render ni ranplase bazdone kont/kredi otomatikman. Gade [FIREBASE.md](FIREBASE.md).
Tès reyèl ekriti/lekti/range/delete ak aksè anonim 403 sou GCS ak Firebase REST
pase. API piblik la pase upload/download tèks ak PNG, HEAD/range, izolasyon ant
kont ak cleanup. Pa gen resous Render peye kreye.

Nouvo esè Google imaj ak tèks echwe ak PROVIDER_QUOTA_EXCEEDED; pa deklare nouvo
jenerasyon sa yo pase. Firebase mache. Firestore poko ranplase bazdone SQLite
tanporè kont/travay/kredi/pwojè yo. Sa toujou anpeche yon deklarasyon pwodiksyon konplè.

50 tès backend pase apre adapter ak spool klip yo. Tès Firebase yo itilize yon
bucket fixture pou write/read/range/delete ak refi credentials machin; yo pa prèv
upload sou Firebase reyèl. Nouvo depandans yo pinnen san chanje vèsyon ki te la yo;
pip check pa jwenn konfli.

## Dènye travay pwodiksyon, 25 oktòb 2026

Download prive kounye a sèvi fichye yo pa moso 64 KiB, sipòte Range/HEAD pou
playback, verifye siyati avan aksè epi rejte move ranges. Proxy web la koupe uploads
twò gwo pandan lekti, san li pa chaje tout demann lan anvan limit la. Endpoint
admin operations bay siyal queue, espas medya ak konfigirasyon san sekrè. Demaraj
pwodiksyon nòmal rejte SQLite/depo manke/origin HTTP/kle siyati enplisit. Beta ki
deklare rete disponib. Adapter S3 prepare pou Supabase san header SSE ki pa sipòte;
limit esè yo rete aplike lè bazdone a vin PostgreSQL.

Chanjman sa yo kounye a enkli nan deploy Firebase a187b45. Itilizatè a gen depo
medya Firebase men bazdone app la poko dirab; li gen Expo/Google Play men aksè teknik yo poko enjekte,
epi kont Apple manke. Gade [koneksyon pwodiksyon](PRODUCTION_CONNECTION.md).

Validasyon nouvo travay la: build Next.js ak TypeScript pase, 2 tès Node sou limit
upload pase, 48 tès backend pase (enkli limit esè sou PG), epi 3 workflow navigatè
pase. Premye esè navigatè a depase 30s pandan demaraj; rerun avèk bidjè 120s ki deja
disponib la fini 3/3 nan 32.2s san chanje assertions. Adapter S3 la teste ak Stubber,
pa yon kont Supabase reyèl. Pa gen nouvo resous Render oswa jenerasyon Google peye.

Aplikasyon devlopman an konstwi dirèkteman nan depo sa a. Li pa yon senp mockup.
Yon beta web piblik sou Render gratis disponib; AAB/IPA ak peman pa fini.

## Fonksyon ki aplike ak konekte

- Next.js/React/TypeScript/Tailwind: akèy, 6 estidyo, bibliyotèk, kredi, paramèt,
  sant èd, kont ak panèl admin. Mak/icon orijinal, tèm nwa ak ekran responsive.
- FastAPI + PostgreSQL: migrasyon vèsyone, enskripsyon, login/logout, sesyon,
  pwofil/lang, ekspòtasyon ak efasman kont/done. Modpas hash scrypt; wòl admin.
- Bouyon tèks: sove, preview, kopi, download, chanje non, efase ak voye nan lòt estidyo.
- Upload imaj/odyo/videyo/tèks: verifye kalite ak gwosè, image decoding ak FFmpeg,
  preview/playback epi lyen prive siyen ki ekspire. Storage lokal prive oswa adapter S3.
- Queue PostgreSQL dirab + Redis wakeups, pwogrè, quality_check, completed/failed,
  retry limite. Travay entèwonp ki riske double billing mande rekonsilyasyon.
- Kredi: rezèvasyon atomik, konfimasyon pri, deduplication, debit apre fichye valide,
  lage rezèvasyon sou echèk, tranzaksyon ak grant admin audite. Imaj debaz: zewo debit.
- MiniDrama: pwojè, ID pèsonaj/sèn estab, aparans/rad/vwa/referans, nòt kontinwite,
  dyalòg egzak, lòd sèn, kontwòl vèsyon, jenerasyon yon sèn ak montaj klip chwazi.
- FFmpeg: normalizasyon ak montaj 8–180s, odyo, rezolisyon ak lòd klip verifye;
  pa gen stretching/loop pou kache klip ki twò kout. Final la antre nan bibliyotèk.
- Adapters Google pou tèks, imaj/referans, TTS, Lyria ak Omni. IDs pa aktive otomatikman.
- Expo Router/React Native: kont, estidyo, pwojè/sèn/pèsonaj, bibliyotèk, preview,
  medya, pataj/download, paramèt/lang ak kredi sou menm API a. Sesyon nan SecureStore.
- Fichye entèfas separe pou 9 lang, deteksyon lang ak chwa pèsistan, layout web RTL.
- Scripts enstalasyon/demaraj/tès, Dockerfiles/Compose, GitHub CI ak workflows EAS.

## Prèv validasyon

- 42 tès backend nan suite konplè a pase: kont, izolasyon itilizatè, CSRF, downloads,
  upload, efasman, reset yon sèl fwa, pri/idempotency, depans an paralèl, refund,
  limit imaj, wòl/admin ak pwojè/revizyon.
- Tès montaj itilize videyo reyèl FFmpeg, verifye dire/rezolisyon/odyo **ak koulè
  sèn yo nan bon lòd**. Tès upload → queue → montaj → download epizòd pase.
- Yon lòt tès TLS/reset pase nan suite reset ki gen 3 tès la: 25 tès backend diferan an total.
- 4 tès zouti/lang pase: discovery pagination/erè ak konplè fichye 9 lang yo.
- Build pwodiksyon Next.js ak TypeScript web pase.
- TypeScript mobil ak export Hermes Android/iOS pase; vèsyon SDK soti nan matris
  Expo SDK 58. Pin react-dom 19.3.0 evite yon konfli peer sou fresh npm ci.
- Tès navigatè itilize backend reyèl. Rezilta final yo nan artifacts/VALIDATION.md.
- Alembic check: schema aktyèl la pa bezwen lòt migrasyon.

Tès otomatik backend yo itilize fixtures pou repons founisè a. Esè piblik separe
verifye jenerasyon Google reyèl, sovgad ak download; resi yo nan AI_TRIAL_ACTIVATION.md.
Tès reset valide token/revokasyon; pa gen email SMTP reyèl ki voye.
Tradiksyon yo se yon premye vèsyon; revizyon imen ak tès aksesibilite aparèy rete itil.

## Sa ki rete pou fini pwodwi a

1. **Modèl ak kota:** kle Gemini sou Render, billing konfime, esè reyèl aktive.
   Imaj, tèks, vwa, chante, videyo 8s ak epizòd anviwon 16s pase. Tèks/TTS aktyèl yo ranplase ansyen IDs ki echwe
   malgre yo vizib nan katalòg la. Kalite ak limit kont toujou bezwen siveyans.
2. **Kalite medya:** lyrics egzak odyo, vwa senk lang, lip-sync otomatik, vizyon pou
   detekte defòmasyon/kontinwite, melanj mizik/narasyon ak soutit pa fini.
   Referans ak prompts ede; yo pa garanti figi, rad, dyalòg oswa bouch egzak.
3. **Peman:** Stripe/web, Apple/Google billing, abònman ak pakè kredi pa aplike.
   Pa gen bouton ki fè moun kwè yo achte kredi. Nenpòt entegrasyon mande tès sandbox.
4. **Idantite:** email reset mande SMTP; Google/Apple login, verifikasyon email,
   MFA admin ak kontwòl abi avanse pa aplike.
5. **Mobil/OTA:** sous ak bundles pare pou etap build la; pa gen aparèy oswa native
   build teste, AAB/IPA, rollout/rollback reyèl, store submission oswa EAS publication.
   Bezwen kont Expo, project ID ak signing/developer accounts.
6. **Pwodiksyon:** beta gen hosting/TLS; bezwen depo dirab, bucket prive, moderation,
   backup/restore drill, metrik/alert, rapò erè, audit sekirite ak revizyon LGPD/store.
   Kontenè Render deplwaye; CI GitHub ak pwodiksyon final rete pou valide.

## Faz yo

| Faz | Estati aktyèl |
|---|---|
| 1 | Dokiman Google aktyèl verifye; chwa kont/pri final ak benchmark GPU rete |
| 2 | UI/UX web + mobil, mak ak 9 fichye lang; QA imen/aparèy rete |
| 3 | Backend/kont/bibliyotèk/migrasyon travay; federasyon/MFA/SMTP pwodiksyon rete |
| 4 | Imaj reyèl jenere/sove/download; zewo kredi itilizatè, operatè peye Google |
| 5 | Tèks kreyòl ak WAV 6.04s reyèl sove/download; benchmark plizyè lang rete |
| 6 | Chante MP3 reyèl 66.85s valide; vokal/lyrics/lisans final mande revizyon |
| 7 | Videyo Google 8s/720p ak son valide; montaj 8–180s teste lokalman |
| 8 | Epizòd reyèl 2 sèn/16.10s jenere/sove/download; lip-sync ak QC vizyèl rete |
| 9 | Ledger/retry/refund teste; peman ak abònman pa aplike |
| 10 | Admin debaz, CI ak konfig EAS ekri; native builds/OTA reyèl rete |
| 11 | Pa lanse: bezwen sèvis ekstèn, revizyon pwodiksyon ak tès final |

Enstriksyon kontinye: gade DEPLOYMENT.md. Pa deklare tout pwodwi a fini ak lis sa a.

## Preparasyon Render

Imaj Docker bati epi deplwaye sou sèvis Render gratis la. Twa workflow navigatè
lokal pase. Validasyon PG ak disk dirab te fèt nan yon kontenè separe; beta gratis
la sèvi ak SQLite ak fichye tanporè. Endpoints Render owners/PostgreSQL retounen
HTTP 403; pa gen fallback oswa resous peye kreye.

## Chwa aktyèl: Render gratis

Itilizatè a refize plan Render peye pou kounye a. `render.yaml` gen yon sèl sèvis
gratis, san disk oswa bazdone peye. Avètisman done tanporè nan 9 lang. Esè AI zewo
kredi aktive avèk limit apre itilizatè a mete kle sou Render epi konfime billing
Google. Grant kredi peye rete bloke sou SQLite.

## Lyen piblik verifye

https://haytile-ai.onrender.com sou plan Render Free, estati live. Paj/8 JS-CSS assets
ak API reponn HTTP 200 sou HTTPS verifye. Tès piblik kont/bouyon/download/rename/
pwojè/logout pase. Otomasyon navigatè piblik bloke pa trust/proxy lokal, pa deklare
li pase. Kontenè gratis lokal la pase 3 workflow navigatè yo. Done tanporè; esè AI aktive.

## Preparasyon esè AI reyèl sou hosting gratis

Kòd nouvo a ajoute esè zewo kredi ki mande aktivasyon operatè, limit dire/kantite,
admisyon SQLite atomik, bootstrap modèl kont la, polling/recovery Interactions,
download URI sekirize ak referans plizyè pèsonaj. MiniDrama kapab planifye,
sove pwojè/referans/sèn epi rasanble yon epizòd MP4. Tès pipeline sa a itilize
founisè simulation klèman idantifye ak montaj FFmpeg reyèl. Esè piblik Google reyèl
fèt separeman. 42 tès backend, build web, TypeScript web/mobil ak 4 tès lang/discovery
pase; 7 tès montaj/pwojè pase apre optimizasyon kopi klip natif la.

Kle Google cloud la otorize Google sèlman; itilizatè a mete kle runtime Render la
dirèkteman epi konfime billing. Gade [AI_TRIAL_ACTIVATION.md](AI_TRIAL_ACTIVATION.md).
Pa gen resous Render peye kreye; depans Google rete apa. Videyo limite 8s, epizòd
limite 16s, 2 esè pa estidyo/itilizatè/jou ak 10 demann global/jou pandan beta a.

Dènye deploy 6444483 live. Sis estidyo gen resi jenerasyon reyèl. Epizòd la gen
yon pèsonaj ak referans, de klip AI, dyalòg planifye ki rete egzak, pwojè editable
ak MP4 final prive. Sa pa pwouve dyalòg odyo/lip-sync oswa kontinwite vizyèl pafè.
