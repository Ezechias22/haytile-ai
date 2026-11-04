# HAYTILE AI — estati livrezon

## Koneksyon Stripe pwodiksyon ak BRL

Itilizatè a chwazi kle pwodiksyon. Kle live la verifye ak Stripe, kont BR
pare pou peman kat, webhook live kreye epi sekrè siyen an sove sou Render
san ekspoze li. Sipò BRL ajoute ak pri kredi minimòm R$0.06 sou baz referans
USD/BRL verifye 5.4654 (4 novanm 2026). 123 tès backend ak 4 workflow
billing navigatè pase; transpò reyèl lokal la konsève siyati ak kò webhook
UTF-8 egzakteman. Pa gen chaj kat ni jenerasyon Google nan verifikasyon sa yo.

## Stripe web ak chat mobil pi lejè

Peman Hosted Checkout, abònman pa fakti verifye, pòtay kliyan, webhook siyen,
resi prive ak pwoteksyon kont doub kredi ajoute. Sandbox rete apa de kredi
reyèl; peman reyèl dezaktive jiskaske kle, pri ak tès Stripe reyèl konfigire.
Kle Stripe yo poko disponib nan anviwònman/Render lè entegrasyon an te fèt.
120 tès backend, 8 workflow app ak 3 workflow Stripe nan navigatè pase
avèk founisè lokal. Sandbox Firestore reyèl verifye izolasyon balans,
rezistans kont doub kredi ak retou apre SQL efase; fixture yo netwaye.
Pa gen jenerasyon Google ni tranzaksyon Stripe reyèl nan tès sa yo.
Code `c96c392670f47ca716dd5b97d5fd91f7e6fab573` live sou Render gratis
(deploy `dep-dblk5s0n74is73ac268g`), runtime piblik `stripe-checkout-v6`
ak sous verifye. Admin Stripe prive, webhook san siyati rejte, vokal natif
aktif, balans kont reyèl la pa chanje nan smoke checks. `STRIPE_SECRET_KEY`
ak `STRIPE_WEBHOOK_SECRET` toude absan; koleksyon peman rete dezaktive.
12 tès billing pase apre verifikasyon atomik blokaj ranbousman an.
Gade [STRIPE.md](STRIPE.md) pou etap egzak ak limit aktyèl yo.

Chat mobil la gen bwat yon sèl liy ki grandi lè moun ekri; long nòt yo nan
meni vwa a. Tès 390×844 verifye pati anba <110px ak plis pase 65% ekran pou
konvèsasyon. Vèsyon konpak `141de691ec17c1ee0677f175e929d30536e4e455` live
Render gratis (deploy `dep-dblhj7ijnfac7381nd10`), runtime/source piblik verifye.
Vokal natif deja live depi `859de935ef4c58f3a6868eee3af8f46cc9a9bab5`
(deploy `dep-dblh8agae00c73c8f7i0`), WSS anonim rejte san koneksyon Google.

## Vokal natif an dirèk ak ekran chat fikse

Chemen SpeechRecognition/tèks/TTS ranplase pou bouton konvèsasyon vokal la:
PCM mikwo ale nan Gemini Live, repons PCM jwe an dirèk, entèripsyon vide ke
od yo. Pa kreye mesaj tèks oswa fichye odyo pou apèl sa yo. Dikte yon mesaj
ak lekti odyo yon repons tèks rete fonksyon apa. Tèt app, lateral ak bwat
mesaj rete an plas; konvèsasyon/istorik sèlman defile.
Gade [NATIVE_LIVE_VOICE.md](NATIVE_LIVE_VOICE.md) pou modèl, tarif, limit ak tès.

## Vokal nan bwat mesaj la, san fòm bidjè

Bouton vokal toupre mikwo ak voye mesaj, kòmanse ak yon sèl klik, kanpe ak menm
bouton an. Chwa vwa/modèl nan meni pliab anba bwat mesaj la. Pa gen demann
bidjè oswa modal konfimasyon sesyon. Vwa toujou sèvi ak kredi; pri modèl la
verifye sou backend, balans pa ka vin negatif. Tèks toujou gratis.
5 tès backend vokal, 6 workflow navigatè, build web ak 4 tès konfigirasyon/tradiksyon
pase san jenerasyon Google AI.
Source `568c347de80c3956e37ea35ef81a71075485c42c` live sou Render gratis
(deploy `dep-dblggn59el5s73cvvfb0`), runtime piblik `composer-voice-v4` konfime.

## Konvèsasyon vokal otomatik ak jesyon chat — nouvo livrezon web

Repons vokal otomatik ak vwa/modèl chwazi, plafon kredi valide sou backend,
meni Chats/Studios separe, bouton ouvri/fèmen ba lateral ak efasman chat konfime.
Haytile Topup sèlman pwopoze pou rechaj, gift card ak sèvis dijital ki koresponn;
lyen li yo pa sèvi kòm lyen estidyo AI. Chat tèks rete gratis, imaj/vwa peye.
102 tès backend ak 7 workflow navigatè pase ak founisè lokal, san jenerasyon Google.
Build web, TypeScript mobil ak 4 tès tradiksyon verifye.
Commit `3ceca5b4e77e3b38ef0169d38aa10537796d7990` live sou Render gratis
(deploy `dep-dblg86egekts738b1r90`). Runtime piblik `voice-mode-navigation-v3`
ak SHA konfime. Meni separe, bouton lateral, logo, 30 vwa ak otorizasyon
chat prive verifye. Quotes piblik tèks 0 / imaj 8 / vwa 26 kredi;
balans kont reyèl la pa chanje. Pa gen jenerasyon Google pandan tès/verifikasyon.
Gade [dokiman teknik la](AUTOMATIC_VOICE_AND_CHAT_MANAGEMENT.md).


## Istwa chat sou bò gòch, vwa, logo ak nouvo tarif imaj

Istwa chat yo nan meni prensipal la, Text Studio retire nan UI web, epi chat/odyo
chat pa antre otomatikman nan Mes créations. Enstriksyon AI yo gen enfòmasyon
pwopriyetè a ak lyen ofisyèl haytiles.com / app.haytiles.com / Google Play.
Chat tèks toujou gratis dapre dènye koreksyon itilizatè a. Imaj peye ak quote
obligatwa; ansyen travay zewo-kredi pa chaje apre. Mikwo navigatè + repons TTS
peye ak konfimasyon ajoute. Logo nouvo sou web ak nan sous mobil.
96 tès backend ak 6 workflow navigatè lokal pase san jenerasyon Google peye.
Commit `a4259ab4e1c4ffeb3fe8d07b75b08e729a1cf2d1` live sou Render gratis
(deploy `dep-dbla1ggu01pc739jekg0`). Vèsyon piblik + logo verifye, pa gen Text Studio
nan HTML piblik, 30 vwa ak etikèt gason/fi/net, chat prive konsève. Quotes
piblik verifye: tèks 0, imaj Lite 8, vwa Lite 26 kredi pou ti tèks.
Balans kont reyèl la pa chanje pandan smoke checks yo; 0 jenerasyon Google peye. Gade [SIDEBAR_VOICE_AND_IMAGE_BILLING.md](SIDEBAR_VOICE_AND_IMAGE_BILLING.md).

## Nouvo chat ak kreyasyon dirab — deplwaye sou web

Chat HAYTILE ajoute ak istwa, kontèks, prezantasyon AI, chwa modèl ak repons
nan menm fil la. Metadata travay/bibliyotèk/pwojè ak debi jenerasyon deplase sou
Firestore atomik; imaj ak tèks gratis. Nouvo quotes pwoteje depans modèl chè yo;
UI montre etap reyèl, tit otomatik modifyab, 30 vwa TTS ak dire 8–180s.
93 tès backend, 5 workflow navigatè (chat, jenerasyon, kont/brouyon,
navigasyon mobil ak storyboard), build web,
TypeScript mobil, tradiksyon ak limit proxy pase. Vrè Firestore verifye
rezèvasyon/debi + retou travay/rezilta/pwojè apre SQL efase sou kont jetab.
Pa gen jenerasyon Google peye.
Commit `de567c39f10f03f663f7c11795cdc93a4eff562b` live sou Render gratis
(deploy `dep-dbl7vuutlv9c73b8qjkg`). API piblik + HTML konfime menm
vèsyon an, chat prive, finans admin aktif, 30 vwa, 36 chwa pa estidyo,
imaj/tèks 0 kredi ak dire 180s. Quotes piblik: mizik default 32, videyo
180s 10,258, epizòd 180s 11,158. Pa gen balans reyèl ki modifye nan smoke
checks yo; pa gen jenerasyon Google peye. Achiv legacy anvan deplwaman
verifye 2 kont, 0 metadata travay/rezilta/pwojè ak 0 travay aktif.
Nou pa reklame rekiperasyon ansyen kreyasyon ki te deja pèdi metadata yo.
Gade [CHAT_AND_DURABLE_CREATIONS.md](CHAT_AND_DURABLE_CREATIONS.md).

Seksyon ki anba yo se resi istorik; limit ansyen vèsyon yo pa estati nouvo sous la.

## Balans ak plan Firestore, jenerasyon reaktive

Ajout kredi ak plan manyèl deplase sou Firestore (wallet + event + audit atomik,
idempotency ak kontwòl vèsyon). /me, /wallet, export ak admin montre balans reyèl,
ki rete apre SQL efase. 83 tès backend pase; tès vrè Firebase ajoute 100 + 25
epi konfime 125 ak yon sèl event pou demann repete. Pa gen jenerasyon Google
peye teste. Itilizatè a konfime Google rechaje epi mande pou nou pa depanse
kredi yo nan tès. Debi Haytile pa jenerasyon toujou bloke jiskaske travay yo
gen depo pèmanan; modèl zewo-kredi yo ka sèvi ak faktirasyon Google operatè a.
Deploy `09ec380` live epi vèsyon API piblik la verifye. Tès piblik sou kont jetab
konfime 13 kredi san double-ajout + plan 7 kredi = 20. Jenerasyon/worker aktive
ak sis estidyo disponib dapre metadata. Pa gen jenerasyon Google peye teste.
Shell web la pa kenbe ansyen vèsyon an nan kach yon ane ankò.
Gade [WALLETS.md](WALLETS.md).

## Kont ki rete apre redeplwaman

Sous kont/sesyon yo deplase sou Firestore avèk menm UUID, hash modpas, pwofil,
lang ak wòl admin. SQL se kopi idantite lokal sèlman. Tès bazdone lokal efase,
reset/revokasyon, pann Firestore, email inik ak kont efase pa resisite ajoute.
Vrè Firestore ak de pwosesis API separe/de SQLite vid verifye menm sesyon/modpas/ID
restaure. 78 tès backend, 4 workflow navigatè, build web ak TypeScript mobil pase.
Wallet/travay/pwojè/metadata bibliyotèk poko migre; finans rete bloke
sou SQLite. Deploy `9160fc9` live; yon kont piblik tès kenbe menm ID/modpas/sesyon
apre yon dezyèm vrè redeplwaman Render. Import SQL dezaktive apre pasaj la.
Gade [ACCOUNT_PERSISTENCE.md](ACCOUNT_PERSISTENCE.md).

## Panèl administratè prive

Ajoute lis itilizatè ak rechèch/pajinasyon, balans, plan/dat ekspirasyon, atribisyon
manyèl Free/Creator/Pro ak kredi yon sèl fwa, audit ak aktivasyon pwopriyetè avèk
sesyon + imel sèvè + kòd prive. Pa gen pwomosyon otomatik selon imel sèlman.
Repetisyon demann pa double kredi; tranzaksyon plan/kredi/audit atomik sou PostgreSQL.
71 tès backend pase; workflow navigatè lokal verifye login/aktivasyon/rechèch,
ajout 25 kredi ak plan Creator + 10 kredi (balans final 35). Twa ansyen workflow
navigatè yo pase tou. Build web, TypeScript mobil ak 4 tès lang/discovery pase.

LIMIT LIVE: kont/kredi/travay yo toujou SQLite tanporè. Bouton finansye yo bloke
sou sèvè ak nan UI jiskaske kont/wallet yo gen depo pèmanan. Firebase medya ak
kontè pa reprezante migrasyon kont yo. Pa gen peman oswa renouvèlman otomatik;
plan yo se etikèt manyèl ak kredi eksplisit. Gade [ADMIN.md](ADMIN.md). Deploy `8094e3a` live sou Render gratis; endpoint
admin yo refize demann san koneksyon (401). Imel pwopriyetè konfigire; kòd
aktivasyon prive a poko mete nan Render, kidonk pa gen kont live ki pwomote.


## Lis modèl AI pa estidyo

Selektè modèl ajoute nan web ak sous mobil. Preferans rete sou aparèy la; backend
verifye allowlist/estidyo/pri epi sove modèl chwazi a nan travay la. Pri kredi soti
sèlman sou sèvè; chanje modèl ak menm kle idempotency bay konfli. Modèl anviwònman
yo verifye nan katalòg kont lan anvan yon nouvo travay. Imaj rete zewo kredi.

66 tès backend pase, build web, TypeScript web/mobil ak 4 tès lang/discovery pase.
Lis la sòti nan metadata read-only; pa gen jenerasyon peye lanse. AI/worker rete
an poz paske pa gen kredi API. Gade [MODEL_CHOICES.md](MODEL_CHOICES.md).

Deploy 3f73880 live sou Render gratis. API piblik la retounen 11 chwa pa estidyo
(9 modèl diferan), ak jenerasyon/worker toujou an poz. Verifikasyon navigatè lokal
konfime preferans modèl la rete apre rafrechisman ak chanjman estidyo.

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
