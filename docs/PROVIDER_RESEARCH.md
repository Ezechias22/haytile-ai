# Google AI — sous ofisyèl ki li nan sesyon sa a

Mizajou 24 oktòb 2026 (lè kliyan an). Aksè Google mache, kle backend Render
konfigire epi billing konfime. Sis estidyo pase jenerasyon reyèl, sovgad ak download;
gade [resi egzak yo](AI_TRIAL_ACTIVATION.md). Modèl ki vizib nan katalòg la pa
nesesèman disponib pou nouvo itilizatè: esè reyèl jwenn yon 404 sou ansyen tèks la.

## Modèl ak tarif piblik obsève

Pri USD yo soti nan [tab pri ofisyèl](https://ai.google.dev/gemini-api/docs/pricing),
li avèk HTTP 200 nan sesyon sa a. Yo pa yon quote pou kont ou, yo ka chanje,
epi taks, storage, egress, retry ak lòt token kapab ajoute depans.

| Itilizasyon | ID piblik obsève | Tarif estanda obsève | Nivo gratis |
|---|---|---|---|
| Tèks / planifikasyon | `gemini-3.5-flash-lite` | $0.30 / milyon token antre; $2.50 / milyon token sòti | paj la montre antre/sòti gratis sou Free tier, ak kota |
| Imaj ekonomik Google | `gemini-3.1-flash-lite-image` | $0.25 / milyon token antre; $30 / milyon token imaj sòti; ekivalan $0.0336 pou yon imaj 1K, plis antre/tèks | pa disponib gratis nan tab la |
| Imaj Google | `gemini-3.1-flash-image` | ekivalan $0.067 pou imaj 1K; lòt dimansyon gen lòt tarif | pa disponib gratis nan tab la |
| Chante | `lyria-3.5` | $0.08 / chante | pa disponib gratis nan tab la |
| Klip mizik | `lyria-3-clip-preview` | $0.04 / chante 30 segonn | pa disponib gratis nan tab la |
| Vwa | `gemini-3.8-flash-lite-tts` | $0.50 / milyon token tèks antre, $6 / milyon token odyo sòti jiska 31 desanm 2026; $1 / $12 depi 1 janvye 2027 | paj la montre gratis sou Free tier, ak kota |
| Videyo | `gemini-omni-1.1-flash` | $1.50 / milyon token antre, $17.50 / milyon token videyo sòti; ekivalan apeprè $0.10 / segonn 720p nan nòt Google la; tèks sòti separe | paid tier sèlman |

Kandida ekonomik yo aktive sèlman sou beta a apre konfimasyon operatè ak esè reyèl.
Google montre lòt modèl tou; li pa nesesè peye pou modèl ki pi chè a pou chak travay.
Yon videyo 180s ka koute apeprè $18 pou videyo sòti sèlman nan ekivalan tarif sa a,
anvan antre, planifikasyon, klip depase ak retry. Pa vann yon quote sou estimasyon sa a.

## Chanjman API enpòtan

- [Videyo](https://ai.google.dev/gemini-api/docs/video) endike Veo 3.1 Preview yo
  fèmen 22 oktòb 2026. Pa itilize ansyen IDs kòm default.
- [Omni](https://ai.google.dev/gemini-api/docs/omni): `POST /v1beta/interactions`,
  `response_format.type=video`, `aspect_ratio` 16:9/9:16, 720p default.
  REST retounen blòk videyo nan `steps[].content[]`, avèk done base64.
  Dokiman an di kalite lang lòt pase anglè poko evalye; pa pwomèt dyalòg kreyòl pafè.
- [Mizik](https://ai.google.dev/gemini-api/docs/music-generation): Lyria 3.5 kreye
  chante ak estrikti/vokal; API Interactions, MP3 pa default. Lyrics pèsonalize
  ka antre nan prompt, men sa pa garanti lyrics egzak nan odyo a.
- [Vwa](https://ai.google.dev/gemini-api/docs/speech-generation): adapter generateContent
  li inlineData; PCM konvèti an WAV sou backend. Sa rete pou teste sou modèl kont lan.
- [Imaj](https://ai.google.dev/gemini-api/docs/image-generation): pa sipoze tout modèl
  tèks sipòte imaj. Reference image, aspect ratio ak rezolisyon dwe verifye pou ID a.

## Kota, rejyon, vi prive ak lisans

[Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) di limit aktif yo
vizib nan AI Studio, depann de tier ak estati pwojè; kapasite pa garanti. Pa gen
valè RPM/RPD envante nan kòd la. Limit Haytile yo se limit pwòp aplikasyon an.

[Rejyon](https://ai.google.dev/gemini-api/docs/available-regions) ak
[tèm](https://ai.google.dev/gemini-api/terms) te retounen HTTP 200. Operatè a dwe
verifye peyi billing/deplwaman ak kondisyon ki aplike pou kont li anvan lansman.
Tab pri a distenge tretman done Free/Paid tiers; pa voye done sansib oswa kontni
kliyan sou yon tier san revizyon kondisyon sou itilizasyon done ak konsantman.
Tèm copyright/konsantman vwa, moderation ak règleman store mande revizyon legal;
presans yon modèl nan API pa prèv dwa komèsyal pou tout kontni antre/sòti.

## Imaj gratis pou itilizatè

Backend la aplike zewo debi kredi pou imaj debaz, endepandan pri modèl la. Si
Google peye se founisè aktif a, Haytile peye API a. Pa gen pwomès GPU gratis.
Limit default dev yo se 8 travay imaj pa kont nan 24h, 3 travay an paralèl, ak
100 nouvo travay global pa 24h. Sa pa yon bidjè USD oswa yon defans spam konplè.

Kandida open-weight FLUX la poko gen lisans/resous verifye nan anviwònman sa a:
Hugging Face te retounen HTTP 401. Pa gen pwa telechaje ni GPU benchmark. Pa sèvi
ak li an pwodiksyon jiskaske lisans, kontni, VRAM, kalite ak depans mezire.

## Expo

Sit docs.expo.dev te toujou refize demann sa yo. Sous ofisyèl Expo sou GitHub
te li avèk siksè:

- https://raw.githubusercontent.com/expo/expo/main/docs/pages/eas-update/introduction.mdx
- https://raw.githubusercontent.com/expo/expo/main/docs/pages/eas-update/runtime-versions.mdx

SDK 58 a enstale dapre `expo/bundledNativeModules.json`. `expo install --check`
pa jwenn dezakò lokal an mòd offline; validasyon sou React Native Directory te
bloke. TypeScript ak export Hermes Android/iOS yo pase. Sa pa ranplase yon native
build, yon tès aparèy oswa yon EAS Update reyèl.
