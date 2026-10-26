"""Build signs.json + WebP images from the gazette annex crops.

Usage: python -I build_signs.py <signs_dir> <dest_json> <dest_media_dir>
Names/descriptions follow Iteka rya Perezida n° 85/01 (imigereka 1-6), lightly copy-edited.
"""
import json
import os
import sys

from PIL import Image

signs_dir, dest_json, dest_media = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(dest_media, exist_ok=True)

CATEGORIES = [
    ("biburira", "Ibyapa biburira", "Mpandeshatu ifite umuzenguruko utukura: bikuburira ko imbere hari icyago, bigusaba kwitonda bidasanzwe.", "A"),
    ("gutambuka-mbere", "Ibyapa byo gutambuka mbere", "Bigena uzatambuka mbere mu nkomane cyangwa mu mfunganwa.", "B"),
    ("bibuza", "Ibyapa bibuza", "Uruziga rufite umuzenguruko utukura: bikubuza igikorwa runaka.", "C"),
    ("bitegeka", "Ibyapa bitegeka", "Uruziga rw'ubururu: bigutegeka icyo ugomba gukora.", "D"),
    ("biyobora", "Ibyapa biyobora", "Urukiramende rw'ubururu: biguha amakuru n'icyerekezo.", "E"),
    ("nyongera", "Utwapa nyongera n'ibigoboka abagenzi", "Byuzuza ibindi byapa cyangwa byerekana serivisi ziri hafi.", "F"),
    ("imirongo", "Ibimenyetso byo mu muhanda", "Imirongo n'ibishushanyo biri mu muhanda ubwawo.", "M"),
]

# (file, code, name, description). Codes repeated with a suffix are variants of one sign.
SIGNS = [
    # ---------------------------------------------------------------- A: biburira
    ("p04_00", "A.1a", "Ikoni ibumoso", "Ahegereye ikoni riteza ibyago riri ibumoso."),
    ("p04_01", "A.1b", "Ikoni iburyo", "Ahegereye ikoni riteza ibyago riri iburyo."),
    ("p04_02", "A.1c", "Amakoni akurikiranye, irya mbere ibumoso", "Amakoni abiri cyangwa uruhererekane rw'amakoni arenga abiri, irya mbere riri ibumoso."),
    ("p04_03", "A.1d", "Amakoni akurikiranye, irya mbere iburyo", "Amakoni abiri cyangwa uruhererekane rw'amakoni arenga abiri, irya mbere riri iburyo."),
    ("p04_04", "A.2", "Akamanuko gashobora gutera ibyago", "Ahegereye akamanuko gateye ibyago. Ikigereranyo gishobora kuzuzwa n'ingano y'agacuri ku ijana (%)."),
    ("p04_05", "A.3", "Akazamuko gashinze cyane", "Ahegereye akazamuko gashinze cyane. Ikigereranyo gishobora kuzuzwa n'ingano y'agacuri ku ijana (%)."),
    ("p04_06", "A.4a", "Ifungana ry'umuhanda", "Ahegereye aho umuhanda ufungana ku mpande zombi."),
    ("p04_07", "A.4b", "Ifungana ry'umuhanda ibumoso", "Umuhanda ufungana bitewe n'akayira gasatira umuhanda ku ruhande rw'ibumoso."),
    ("p04_08", "A.4c", "Ifungana ry'umuhanda iburyo", "Umuhanda ufungana bitewe n'akayira gasatira umuhanda ku ruhande rw'iburyo."),
    ("p05_00", "A.5", "Uguhinguka ku mwaro", "Ahegereye aho umuhanda uhingukira ku mwaro, ku nkombe cyangwa ku cyome."),
    ("p05_01", "A.6", "Umuhanda utaringaniye", "Ahegereye ibinogo, utununga cyangwa ahantu umuhanda umeze nabi."),
    ("p05_02", "A.7", "Umuhanda unyerera", "Ahegereye igice cy'umuhanda gishobora kunyerera."),
    ("p05_03", "A.8", "Utubuye dutaruka", "Ahegereye igice cy'umuhanda aho utubuye dushobora gutaruka."),
    ("p05_04", "A.9", "Amabuye ahanuka", "Ahegereye igice cy'umuhanda gishobora kugwamo amabuye ahanuka cyangwa kubamo amabuye. Ikigereranyo gishobora gucurikwa bitewe n'uruhande ibyago biturukamo."),
    ("p05_05", "A.10", "Abanyamaguru", "Ahegereye inzira y'abanyamaguru."),
    ("p05_06", "A.11", "Abana", "Ahegereye aho abana banyura, nko hafi y'ishuri cyangwa y'ikibuga cy'imikino."),
    ("p05_07", "A.12", "Aho abanyamagare bahingukira", "Ahegereye aho abanyamagare binjirira mu muhanda cyangwa bawambukiranya."),
    ("p05_08", "A.13", "Akayira k'amatungo", "Igice cy'umuhanda gishobora kwambukiranywa n'amatungo ku buryo budasanzwe."),
    ("p05_09", "A.14", "Akayira k'inyamaswa", "Igice cy'umuhanda gishobora kwambukiranywa n'inyamaswa ku buryo budasanzwe."),
    ("p05_10", "A.15", "Imirimo", "Ahegereye igice cy'umuhanda gikorerwamo imirimo."),
    ("p05_11", "A.16", "Ibimenyetso bimurika", "Ahegereye aho kugendera mu muhanda bigengwa n'ibimenyetso by'amatara y'amabara atatu."),
    ("p05_12", "A.17", "Ikibuga cy'indege", "Ahegereye aho indege zigurukira hasi hejuru y'umuhanda zigwa cyangwa zihaguruka."),
    ("p05_13", "A.18", "Umuyaga w'intambike", "Ahegereye igice cy'umuhanda gikunze guhuhwamo n'inkubi y'umuyaga w'intambike."),
    ("p05_14", "A.19", "Umuhanda ubisikanirwamo", "Ahegereye igice cy'umuhanda kibisikanirwamo by'agateganyo cyangwa buri gihe, kandi mbere yacyo hagendwaga mu cyerekezo kimwe."),
    ("p06_00", "A.20", "Inkomane", "Ahegereye inkomane. Gutambuka mbere bikurikiza amategeko rusange: ureka ibinyabiziga bituruka iburyo bwawe."),
    ("p06_01", "A.21a", "Umuhanda urasukira ibumoso", "Inkomane aho umuhanda urasukira ibumoso mu mfuruka yenda kuba igororotse. Gutambuka mbere hakurikijwe amategeko rusange."),
    ("p06_02", "A.21b", "Umuhanda urasukira iburyo", "Inkomane aho umuhanda urasukira iburyo mu mfuruka yenda kuba igororotse. Gutambuka mbere hakurikijwe amategeko rusange."),
    ("p06_03", "A.21c", "Umuhanda urasukira ibumoso mu mfuruka ifunganye", "Inkomane aho umuhanda urasukira ibumoso mu mfuruka ifunganye. Gutambuka mbere hakurikijwe amategeko rusange."),
    ("p06_04", "A.21d", "Umuhanda urasukira iburyo mu mfuruka ifunganye", "Inkomane aho umuhanda urasukira iburyo mu mfuruka ifunganye. Gutambuka mbere hakurikijwe amategeko rusange."),
    ("p06_05", "A.21e", "Amasangano ameze nka T", "Inkomane aho umuhanda ugana ibumoso n'iburyo, ariko umuhanda urimo ntukomeze."),
    ("p06_06", "A.21f", "Amasangano ameze nka Y", "Inkomane aho umuhanda usatukamo imihanda ibiri itandukanye."),
    ("p06_07", "A.21h", "Uruhererekane rw'inkomane", "Inkomane zikurikiranye. Gutambuka mbere hakurikijwe amategeko rusange."),
    ("p06_08", "A.22a", "Inkomane ku muhanda utambukwamo mbere", "Ahegereye inkomane aho umuhanda urimo (ugaragazwa n'umurongo munini) utambukwamo mbere y'imihanda isanganya. Ibyapa A.22a kugeza kuri A.22e bizasimburwa n'ibyapa B.3."),
    ("p06_09", "A.22b", "Inkomane ku muhanda utambukwamo mbere", "Umuhanda w'ibumoso urasukira mu muhanda wawe utambukwamo mbere. Ibyapa A.22 bizasimburwa n'ibyapa B.3."),
    ("p06_12", "A.22c", "Inkomane ku muhanda utambukwamo mbere", "Umuhanda w'iburyo urasukira mu muhanda wawe utambukwamo mbere. Ibyapa A.22 bizasimburwa n'ibyapa B.3."),
    ("p06_10", "A.22d", "Inkomane ku muhanda utambukwamo mbere", "Umuhanda urasukira ibumoso mu mfuruka ifunganye mu muhanda wawe utambukwamo mbere. Ibyapa A.22 bizasimburwa n'ibyapa B.3."),
    ("p06_11", "A.22e", "Inkomane ku muhanda utambukwamo mbere", "Umuhanda urasukira iburyo mu mfuruka ifunganye mu muhanda wawe utambukwamo mbere. Ibyapa A.22 bizasimburwa n'ibyapa B.3."),
    ("p06_13", "A.23", "Ahegereye icyapa \"Tanga inzira\"", "Kimenyesha mbere (urugero: muri metero 200) ko ugiye kugera ahari icyapa B.1. Kizasimburwa n'icyapa B.1."),
    ("p06_14", "A.24", "Ahegereye icyapa \"STOP\"", "Ahegereye inkomane aho guhagarara akanya gato ari itegeko. Akapa nyongera kari munsi y'icyapa B.1 kerekana intera ibura ngo ugere ku cyapa STOP."),
    ("p06_15", "A.25", "Aho banyura bazengurutse", "Ahegereye inkomane banyuramo bategetswe kuzenguruka (giratoire)."),
    ("p06_16", "A.26", "Gariyamoshi ifite bariyeri", "Ahegereye amasangano y'inzira nyabagendwa n'inzira ya gariyamoshi ibambiye (ifite bariyeri) hose cyangwa mu gice cyayo."),
    ("p07_00", "A.27", "Gariyamoshi idafite bariyeri", "Ahegereye amasangano y'inzira nyabagendwa n'inzira ya gariyamoshi itabambiye (idafite bariyeri)."),
    ("p07_01", "A.28a", "Gariyamoshi: hasigaye metero 150", "Akapa kariho imirongo itatu itukura iberamye, gashyirwa munsi ya A.26 cyangwa A.27 muri metero 150 mbere y'amasangano na gariyamoshi."),
    ("p07_02", "A.28b", "Gariyamoshi: hasigaye metero 100", "Akapa kariho imirongo ibiri itukura iberamye, gashyirwa muri metero 100 mbere y'amasangano na gariyamoshi."),
    ("p07_03", "A.28c", "Gariyamoshi: hasigaye metero 50", "Akapa kariho umurongo umwe utukura uberamye, gashyirwa muri metero 50 mbere y'amasangano na gariyamoshi."),
    ("p07_04", "A.29", "Ibyago", "Ahegereye icyago kidasobanuye ukundi."),
    ("p07_05", "A.30", "Imitemeri y'icyago", "Imitemeri ifite amabara atukura n'ayera asimburana: yerekana icyago kidahoraho, nk'impanuka cyangwa imirimo ikorwa mu muhanda, n'aho bayobereza umuhanda."),
    ("p07_06", "A.31", "Ibitembo by'icyago", "Ibitembo bifite amabara atukura n'ayera asimburana: byerekana icyago kidahoraho kandi bikayobora abagenzi."),
    # ---------------------------------------------------------------- B: gutambuka mbere
    ("p07_07", "B.1", "Tanga inzira", "Gitegeka umuyobozi ugeze ku nkomane guha inzira ibinyabiziga bigenda mu muhanda yegera, ibiturutse iburyo n'ibiturutse ibumoso."),
    ("p07_08", "B.2a", "Hagarara (STOP)", "Gitegeka umuyobozi ugeze ku nkomane guhagarara akanya gato mbere yo kwinjira mu nkomane, no guha inzira ibinyabiziga bigenda mu muhanda yegera."),
    ("p07_09", "B.2b", "Hagarara (STOP), icyapa cya kera", "Gisobanura kimwe n'icyapa B.2a. Ibyapa B.2b bizasimburwa buhoro buhoro n'ibyapa B.2a."),
    ("p07_10", "B.3", "Umuhanda utambukwamo mbere", "Kibwira abagenda muri uyu muhanda ko mu nkomane zawo n'indi mihanda, abaturuka mu yindi mihanda bagomba kubaha inzira."),
    ("p07_11", "B.4", "Iherezo ry'umuhanda utambukwamo mbere", "Kerekana aho uwo muhanda urekera gutambukwamo mbere y'iyindi."),
    ("p07_12", "B.5", "Tanga inzira ku biturutse imbere", "Birabujijwe kwinjira mu muhanda ufunganye aho kubisikana biruhije cyangwa bidashoboka, igihe ikinyabiziga kimwe cyangwa byinshi biturutse imbere bihagarara."),
    ("p08_00", "B.6", "Utambuka mbere y'ibiturutse imbere", "Kereka umuyobozi ugiye kwinjira mu mfunganwa ko afite uburenganzira bwo gutambuka mbere y'ibinyabiziga biturutse imbere. Icyitonderwa: iyo ikizamuka n'ikimanuka bihuye, ikimanuka ni cyo gitanga inzira."),
    ("p08_01", "B.7a", "Inkomane na gariyamoshi", "Kerekana inkomane y'umuhanda n'inzira ya gariyamoshi."),
    ("p08_02", "B.7b", "Inkomane na gariyamoshi y'amashami abiri", "Kerekana ko inzira ya gariyamoshi ihura n'umuhanda ifite nibura amashami abiri."),
    # ---------------------------------------------------------------- C: bibuza
    ("p08_03", "C.1", "Ntihanyurwa muri iki cyerekezo", "Nta kinyabiziga kihanyura mu cyerekezo uganamo."),
    ("p08_04", "C.2a", "Ntihanyurwa mu byerekezo byombi", "Habujijwe kunyurwa n'ikinyabiziga icyo ari cyo cyose, mu byerekezo byombi."),
    ("p08_05", "C.2b", "Ntihanyurwa uretse abahatuye", "Nta kinyabiziga kihanyura uretse iby'abahatuye n'ibigomba guhagarara mu gice cy'inzira giherwa n'iki kimenyetso."),
    ("p08_06", "C.3a", "Ntihanyurwa n'ibinyabiziga bifite moteri", "Ntihanyurwa n'ikinyabiziga icyo ari cyo cyose gifite moteri, uretse amapikipiki adafite akanyabiziga ko ku ruhande na velomoteri."),
    ("p08_07", "C.3b", "Ntihanyurwa n'amapikipiki", "Birabujijwe kuhanyuza ipikipiki."),
    ("p08_08", "C.3c", "Ntihanyurwa n'amagare", "Ntihanyurwa n'ibinyamitende (amagare)."),
    ("p08_09", "C.3d", "Ntihanyurwa na velomoteri", "Birabujijwe kuhanyuza velomoteri."),
    ("p08_10", "C.3e", "Ntihanyurwa n'ibitwara ibicuruzwa", "Ntihanyurwa n'ibinyabiziga bigenewe gutwara ibicuruzwa. Akapa nyongera gashobora kwerekana uburemere baheraho babuza."),
    ("p09_00", "C.3f", "Ntihanyurwa n'ibikurura romoruki", "Ntihanyurwa n'ikinyabiziga icyo ari cyo cyose gikurura romoruki itari makuzungu cyangwa romoruki ifite umutambiko umwe."),
    ("p09_02", "C.3g", "Ntihanyurwa n'abanyamaguru", "Birabujijwe ko abanyamaguru bahanyura."),
    ("p09_01", "C.3h", "Ntihanyurwa n'ibikururwa n'inyamaswa", "Ntihanyurwa n'ibinyabiziga bikururwa n'inyamaswa."),
    ("p09_03", "C.3i", "Ntihanyurwa n'utunyamitwaro dusunikwa", "Ntihanyurwa n'utunyamitwaro dusunikwa (ingorofani n'ibindi)."),
    ("p09_04", "C.3j", "Ntihanyurwa n'imashini zihinga", "Ntihanyurwa n'ibinyabiziga bihinga bifite moteri."),
    ("p09_05", "C.4a", "Ntihanyurwa n'amoko yerekanwe", "Ntihanyurwa n'amoko y'ibinyabiziga cyangwa abagenzi bashushanyijwe ku cyapa (urugero: imodoka n'ipikipiki)."),
    ("p09_06", "C.4b", "Ntihanyurwa n'amoko yerekanwe", "Ntihanyurwa n'amoko y'ibinyabiziga cyangwa abagenzi bashushanyijwe ku cyapa (urugero: ibikururwa n'inyamaswa)."),
    ("p09_07", "C.5", "Ubugari ntarengwa", "Ntihanyurwa n'ibinyabiziga bifite ubugari burenze ubwerekanwa ku cyapa (muri metero)."),
    ("p09_08", "C.6", "Ubuhagarike ntarengwa", "Ntihanyurwa n'ibinyabiziga bifite ubuhagarike, habariwemo imizigo, burenze ubwerekanwa ku cyapa (muri metero)."),
    ("p09_09", "C.7", "Uburemere ntarengwa", "Ntihanyurwa n'ibinyabiziga bifite uburemere burenze ubwerekanwa ku cyapa (muri toni)."),
    ("p09_10", "C.8", "Uburemere ntarengwa ku mutambiko", "Ntihanyurwa n'ibinyabiziga bifite uburemere ku mutambiko burenze ubwerekanwa ku cyapa (muri toni)."),
    ("p09_11", "C.9", "Uburebure ntarengwa", "Ntihanyurwa n'ibinyabiziga cyangwa ibinyabiziga bikomatanye bifite uburebure, habariwemo imizigo, burenze ubwerekanwa ku cyapa (muri metero)."),
    ("p09_12", "C.10", "Intera ntarengwa hagati y'ibinyabiziga", "Birabujijwe kugenda udasize hagati yawe n'ikinyabiziga kikuri imbere intera nibura ingana n'iyerekanwe ku cyapa (muri metero)."),
    ("p10_00", "C.11a", "Birabujijwe gukatira ibumoso", "Birabujijwe gukata mu cyerekezo cyerekanwa n'akarangacyerekezo (ibumoso)."),
    ("p10_01", "C.11b", "Birabujijwe gukatira iburyo", "Birabujijwe gukata mu cyerekezo cyerekanwa n'akarangacyerekezo (iburyo)."),
    ("p10_02", "C.12", "Birabujijwe guhindukira", "Birabujijwe guhindukira ugasubira inyuma (demi-tour)."),
    ("p10_03", "C.13a", "Birabujijwe kunyuranaho", "Birabujijwe kunyura ku binyabiziga byose, uretse ibinyamitende."),
    ("p10_04", "C.13b", "Amakamyo abujijwe kunyuranaho", "Kubuza kunyuranaho ku binyabiziga bitwara ibicuruzwa bifite uburemere ntarengwa burenga toni 3,5. Akapa nyongera gashobora kwerekana ubundi buremere."),
    ("p10_05", "C.14", "Umuvuduko ntarengwa", "Umuvuduko ntugomba kurenga uwerekanwa ku cyapa (mu birometero ku isaha)."),
    ("p10_06", "C.15", "Birabujijwe kuvuza amahoni", "Birabujijwe kuvuza ihoni, keretse iyo ari ukwirinda impanuka."),
    ("p10_07", "C.16", "Hagarara kuri gasutamo", "Birabujijwe gutambuka udahagaze akanya gato, kubera gasutamo cyangwa indi mpamvu yanditse ku cyapa."),
    ("p10_08", "C.17a", "Iherezo ry'ibibuzwa byose", "Kerekana ko ibibuzwa byose byari byerekanywe n'ibyapa ku binyabiziga bigenda bitagikurikizwa."),
    ("p10_09", "C.17b", "Iherezo ry'umuvuduko ntarengwa", "Kerekana ko umuvuduko ntarengwa werekanywe n'icyapa C.14 utagikurikizwa."),
    ("p10_10", "C.17c", "Iherezo ryo kubuza kunyuranaho", "Kerekana ko kubuza kunyuranaho kwerekanywe n'icyapa C.13a (cyangwa C.13b) bitagikurikizwa."),
    ("p10_11", "C.18", "Birabujijwe guhagarara umwanya munini", "Kerekana aho ikinyabiziga gitangira kubuzwa guhagarara umwanya munini."),
    ("p11_00", "C.19", "Birabujijwe guhagarara umwanya muto n'umunini", "Kerekana aho ikinyabiziga gitangira kubuzwa guhagarara umwanya muto ndetse n'umwanya munini."),
    ("p11_01", "C.20a", "Guhagarara bisimburana: iminsi 1-15", "Birabujijwe guhagarara umwanya munini ku ruhande iki cyapa kiriho mu minsi 15 ya mbere y'ukwezi."),
    ("p11_02", "C.20b", "Guhagarara bisimburana: iminsi 16-31", "Birabujijwe guhagarara umwanya munini ku ruhande iki cyapa kiriho kuva ku munsi wa 16 kugeza ku munsi wa nyuma w'ukwezi."),
    # ---------------------------------------------------------------- D: bitegeka
    ("p11_03", "D.1a", "Icyerekezo gitegetswe: ibumoso", "Gitegeka buri kinyabiziga gukurikiza icyerekezo cyerekanwa n'akarangacyerekezo."),
    ("p11_04", "D.1a", "Icyerekezo gitegetswe: kata iburyo", "Gitegeka buri kinyabiziga gukatira iburyo nk'uko akarangacyerekezo kabyerekana."),
    ("p11_05", "D.1a", "Komeza imbere cyangwa ukatire iburyo", "Gitegeka kunyura muri kimwe mu byerekezo byerekanwa n'uturangacyerekezo."),
    ("p11_06", "D.1a", "Komeza imbere", "Gitegeka buri kinyabiziga gukomeza imbere."),
    ("p11_07", "D.1b", "Icyerekezo gitegetswe (impande zombi)", "Bisobanura kimwe na D.1a. Kerekana ko ibinyabiziga bishobora kunyura hirya no hino y'inkomyi iri mu nzira nyabagendwa."),
    ("p11_08", "D.1c", "Uguhigama", "Mu nzira ifunganye, kerekana igice cyagutse aho ikinyabiziga gihagarara kugira ngo giheze umwanya ibinyabiziga biturutse imbere."),
    ("p12_00", "D.2", "Ugukikira bitegetswe", "Gishyirwa ku buhungiro cyangwa imbere y'inkomyi: gitegeka kunyura mu ruhande rwerekanwa n'akarangacyerekezo."),
    ("p12_01", "D.3", "Inkomane banyuramo bazengurutse", "Gitegeka buri kinyabiziga gukurikiza amategeko agenga inkomane banyuramo bazengurutse."),
    ("p12_02", "D.4", "Inzira y'amagare itegetswe", "Gitegeka abatwara amagare na velomoteri kunyura muri iyo nzira. Ibindi binyabiziga ntibiyitira."),
    ("p12_03", "D.5", "Inzira y'abanyamaguru itegetswe", "Gitegeka abanyamaguru kunyura muri iyo nzira, kikabuza abandi bagenzi kuyinyuramo."),
    ("p12_04", "D.6", "Inzira y'abagendera ku mafarasi", "Kimenyesha abagendera ku mafarasi ko bagomba kunyura muri iyo nzira, kikabuza abandi kuyinyuramo."),
    ("p12_05", "D.7", "Inzira y'amatungo itegetswe", "Kimenyesha abayobozi b'amatungo ko bagomba kuyanyuza muri iyo nzira."),
    ("p12_06", "D.8", "Umuvuduko muto ntarengwa", "Ibinyabiziga biri muri iyo nzira bigomba kugira nibura umuvuduko werekanwe (mu birometero ku isaha)."),
    ("p12_07", "D.9", "Iherezo ry'umuvuduko muto ntarengwa", "Kerekana aho umuvuduko muto wari utegetswe n'icyapa D.8 utagitegetswe."),
    # ---------------------------------------------------------------- E: biyobora
    ("p13_00", "E.1a", "Kumenyesha mbere icyerekezo", "Urugero rw'icyapa kimenyesha abagenzi ibyerekezo biri mu masangano begereye."),
    ("p13_02", "E.1b", "Kumenyesha mbere icyerekezo", "Urugero rw'icyapa kimenyesha ibyerekezo by'amasangano ameze nka Y."),
    ("p13_01", "E.1c", "Kumenyesha mbere icyerekezo", "Urugero rw'icyapa kimenyesha ibyerekezo n'intera bijyayo."),
    ("p13_03", "E.2a", "Umuhanda udakomeza", "Urugero rw'icyapa kimenyesha mbere ko umuhanda wo ku ruhande udakomeza."),
    ("p13_04", "E.2b", "Umuhanda udakomeza", "Urugero rw'icyapa kimenyesha mbere ko umuhanda udakomeza."),
    ("p13_05", "E.3", "Inzira igomba kunyurwamo", "Kimenyesha mbere inzira yo kunyuramo ngo ufate icyerekezo cy'ibumoso, igihe gukatira ibumoso bibujijwe mu nkomane ikurikira."),
    ("p13_06", "E.4", "Igisate cyo gufata", "Kimenyesha mbere igisate cy'umuhanda ugomba gufata bitewe n'icyerekezo ushaka gufata mu nkomane."),
    ("p13_08", "E.5a", "Icyerekezo cy'ahantu", "Urugero rw'icyapa kiranga icyerekezo n'intera bijya ahantu runaka."),
    ("p13_07", "E.5b", "Icyerekezo cy'ahantu", "Urugero rw'icyapa kiranga ibyerekezo bijya mu turere dutandukanye."),
    ("p13_09", "E.5c", "Kuyobya umuhanda (DEVIATION)", "Kerekana icyerekezo cyo gukurikira igihe inzira yahinduwe kubera imirimo."),
    ("p14_00", "E.6", "Ikibuga cy'indege", "Kerekana icyerekezo cy'ikibuga cy'indege."),
    ("p14_01", "E.7", "Ikibanza cy'ingando", "Kerekana aho ikibanza cy'ingando giherereye."),
    ("p14_02", "E.8", "Icumbi ry'urubyiruko", "Kerekana aho icumbi ry'urubyiruko riherereye."),
    ("p14_03", "E.9", "Kwinjira mu nsisiro", "Kimenyesha ko winjiye mu nsisiro (umudugudu cyangwa umujyi). Amategeko yo mu nsisiro, nk'umuvuduko ntarengwa, atangira gukurikizwa."),
    ("p14_04", "E.10", "Iherezo ry'insisiro", "Kerekana iherezo ry'insisiro (umudugudu cyangwa umujyi)."),
    ("p14_05", "E.11", "Inzira y'abanyamaguru", "Kereka abanyamaguru n'abayobozi aho inzira y'abanyamaguru iri."),
    ("p14_06", "E.12", "Ibitaro", "Gisaba abayobozi kwitonda hafi y'amavuriro, cyane cyane birinda urusaku rw'amahoni n'urwa moteri."),
    ("p14_07", "E.13a", "Icyerekezo kimwe", "Iyo giteye nyanguni ku murongo ugabanya umuhanda mo kabiri, cyemeza ko uri mu nzira y'icyerekezo kimwe."),
    ("p14_08", "E.13b", "Icyerekezo kimwe", "Iyo giteye kibangikanye n'umuhanda, cyemeza ko umuhanda ugana mu cyerekezo cy'akarangacyerekezo ari uw'icyerekezo kimwe."),
    ("p14_09", "E.14", "Inzira idakomeza", "Kerekana ko inzira giteyeho idakomeza (impera y'inzira)."),
    ("p14_10", "E.15", "Umuhanda urombereje w'ibice byinshi", "Kerekana aho amategeko yo kugendera mu muhanda urombereje w'ibisate byinshi (autoroute) atangirira gukurikizwa."),
    ("p15_00", "E.16", "Iherezo ry'umuhanda urombereje", "Kerekana aho amategeko yihariye y'umuhanda urombereje w'ibisate byinshi atagikurikizwa."),
    ("p15_01", "E.17", "Umuhanda ugenewe imodoka", "Kerekana aho amategeko yihariye y'umuhanda ugenewe imodoka atangirira; ntiwunyurwamo n'abanyamaguru cyangwa amatungo."),
    ("p15_02", "E.18", "Iherezo ry'umuhanda ugenewe imodoka", "Kerekana aho amategeko y'icyapa E.17 atagikurikizwa."),
    ("p15_03", "E.19", "Aho bisi zihagarara", "Kerekana ahagenewe guhagararwamo n'imodoka nini zitwara abantu muri rusange."),
    ("p15_04", "E.20", "Parikingi", "Kerekana ahantu hagenewe guhagararamo umwanya munini."),
    ("p15_05", "E.21", "Amabwiriza yihariye", "Kerekana ko hari amabwiriza yihariye yo kugendera mu cyambu cyangwa ku kibuga cy'indege."),
    # ---------------------------------------------------------------- F: nyongera
    ("p16_00", "F.1", "Intera", "Akapa kerekana intera iri hagati y'icyapa n'aho icyago gitangirira cyangwa aho amabwiriza y'icyapa atangira gukurikizwa."),
    ("p16_01", "F.2", "Uburebure bw'igice", "Akapa kerekana uburebure bw'igice giteza ibyago cyangwa bw'ahantu amabwiriza y'icyapa akurikizwa."),
    ("p16_02", "F.3a", "Intera yo kubuza (imbere)", "Iyo gashyizwe kateganye n'umurongo ugabanya umuhanda mo kabiri, kerekana ahantu habujijwe guhagarara, hakurikijwe icyerekezo cy'akarangacyerekezo."),
    ("p16_04", "F.3b", "Intera yo kubuza (impande zombi)", "Kerekana ko ibibujijwe bireba impande zombi z'icyapa ku ntera yerekanwe."),
    ("p16_03", "F.3c", "Intera yo kubuza (inyuma)", "Kerekana intera ibibujijwe bireba, ku ruhande rwerekanwa n'akarangacyerekezo."),
    ("p16_07", "F.4a", "Ibibuzwa bireba imbere", "Akapa kareba igice cy'umuhanda kiri hirya y'ikimenyetso."),
    ("p16_05", "F.4b", "Ibibuzwa bireba impande zombi", "Akapa kareba ibice by'umuhanda biri hirya no hino y'ikimenyetso."),
    ("p16_06", "F.4c", "Ibibuzwa bireba inyuma", "Akapa kareba igice cy'umuhanda kiri hino y'ikimenyetso."),
    ("p16_08", "F.5", "Ikintu ngoboka", "Kerekana ikintu ngoboka gishushanyije ku buso bwera bw'icyapa. Ibyapa F.6 kugeza kuri F.18 ni ingero zacyo."),
    ("p16_09", "F.6", "Ahari ubutabazi", "Kerekana ahari ubutabazi bw'ibanze."),
    ("p17_01", "F.7", "Aho bagobokera ibinyabiziga", "Kerekana aho bakorera cyangwa bagobokera ibinyabiziga (garaje)."),
    ("p17_00", "F.8", "Ahari telefone", "Kerekana ahari telefone."),
    ("p17_02", "F.9", "Ahari lisansi na mazutu", "Kerekana sitasiyo y'ibikomoka kuri peteroli."),
    ("p17_03", "F.10", "Hoteli cyangwa icumbi", "Kerekana hoteli cyangwa ahari icumbi ry'abagenzi."),
    ("p17_04", "F.11", "Aho bafatira ifunguro", "Kerekana resitora cyangwa aho bafatira ifunguro."),
    ("p17_05", "F.12", "Urunywero cyangwa urusamuriro", "Kerekana aho banywera cyangwa basamurira."),
    ("p17_06", "F.13", "Ahateganyirijwe abahisi", "Kerekana ahateganyirijwe kuruhukira no gufatira amafunguro abahisi."),
    ("p17_07", "F.14", "Aho bahagurukira batembera n'amaguru", "Kerekana aho urugendo rwo gutembera n'amaguru rutangirira."),
    ("p17_08", "F.15", "Ikibanza cy'ingando", "Kerekana ikibanza cy'ingando."),
    ("p17_09", "F.16", "Ikibanza cya karavani", "Kerekana ikibanza cyagenewe amazu yimukanwa akururwa n'imodoka (karavani)."),
    ("p17_10", "F.17", "Ikibanza cy'ingando na karavani", "Kerekana ikibanza cy'ingando cyakira n'amazu yimukanwa."),
    ("p17_11", "F.18", "Icumbi ry'urubyiruko", "Kerekana icumbi ry'urubyiruko."),
    # ---------------------------------------------------------------- imirongo yo mu muhanda
    ("p18_00", "M.1", "Umurongo wera udacagaguye", "Umuyobozi wese abujijwe kuwurenga (ingingo ya 110)."),
    ("p18_01", "M.2", "Umurongo wera ucagaguye", "Abujijwe kuwurenga keretse iyo anyura ku kindi kinyabiziga, akatira ibumoso, ahindukira cyangwa ajya mu kindi gisate cy'umuhanda."),
    ("p18_02", "M.3", "Uduce tugufi twegeranye", "Uduce tw'umurongo tugufi kandi twegeranye twerekana ko umurongo udacagaguye wegereje: ntukawurenge."),
    ("p18_03", "M.4", "Umurongo udacagaguye n'ucagaguye bibangikanye", "Umuyobozi yita gusa ku murongo umwegereye. Ushobora kurenga ucagaguye uri ku ruhande rwawe, ariko ntiwarenga udacagaguye uri ku ruhande rwawe."),
    ("p18_04", "M.5", "Igisate cy'ibitwara abantu muri rusange", "Igice gikikijwe n'uduce tugari tw'ibara ryera: gitegeka ibinyabiziga bitwara abantu muri rusange n'ibigenda buhoro kukinyuramo."),
    ("p18_05", "M.6", "Inzira y'amagare", "Igice kigarukira ku mirongo ibiri yera icagaguye ibangikanye, kidafite ubugari buhagije ku modoka: ni inzira y'ibinyamitende."),
    ("p18_06", "M.7", "Umurongo wera ku nkengero y'umuhanda", "Werekana aho umuhanda ugarukira; birabujijwe kuwurenga ugenda, uhagarara umwanya muto cyangwa umunini ku nkengero."),
    ("p19_00", "M.8", "Umurongo w'umuhondo ucagaguye ku nkengero", "Bibujijwe guhagarara umwanya munini ku burebure bw'uwo murongo."),
    ("p19_01", "M.9", "Umurongo wera mugari w'inkengero itari nyayo", "Igice cy'umuhanda kiri hirya y'uwo murongo kigenewe guhagararwamo umwanya muto cyangwa munini."),
    ("p19_02", "M.10", "Imirongo yera yambukiranya y'aho bahagarara", "Yerekana itangiriro n'iherezo by'ahantu hahagararwa, n'imyanya ibinyabiziga bihagararamo."),
]

# Fraction of the height to keep where the automatic label crop cannot separate the printed code.
KEEP_HEIGHT = {
    "p08_07": 0.85,
    "p09_01": 0.88,
    "p09_03": 0.81,
    "p09_06": 0.85,
    "p10_02": 0.85,
    "p13_08": 0.62,
    "p14_00": 0.54,
    "p16_00": 0.66,
    "p16_01": 0.67,
    "p19_02": 0.7,
}


def crop_label(im: Image.Image) -> Image.Image:
    """Cut the printed sign code (A.10, C,3b...) off the bottom of a scan.

    Dark pixels are grouped into connected components; large components form the sign itself and
    small components lying entirely below it are the code label, which is cropped away.
    """
    gray = im.convert("L")
    w, h = gray.size
    px = gray.load()
    dark = [[px[x, y] < 165 for x in range(w)] for y in range(h)]
    seen = [[False] * w for _ in range(h)]
    comps = []
    for y0 in range(h):
        for x0 in range(w):
            if not dark[y0][x0] or seen[y0][x0]:
                continue
            stack = [(x0, y0)]
            seen[y0][x0] = True
            minx = maxx = x0
            miny = maxy = y0
            count = 0
            while stack:
                x, y = stack.pop()
                count += 1
                minx, maxx, miny, maxy = min(minx, x), max(maxx, x), min(miny, y), max(maxy, y)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < w and 0 <= ny < h and dark[ny][nx] and not seen[ny][nx]:
                            seen[ny][nx] = True
                            stack.append((nx, ny))
            comps.append((minx, miny, maxx, maxy, count))
    large = [c for c in comps if (c[3] - c[1]) >= h * 0.16 or ((c[2] - c[0]) >= w * 0.35 and (c[3] - c[1]) >= h * 0.06)]
    if not large:
        return im
    bottom = max(c[3] for c in large)
    below = [c for c in comps if c[1] > bottom and c[4] >= 4]
    if not below or bottom < h * 0.5:
        return im
    return im.crop((0, 0, w, min(h, bottom + 3)))

cat_by_letter = {c[3]: c[0] for c in CATEGORIES}
seen_codes: dict[str, int] = {}
out = []
for file, code, name, desc in SIGNS:
    n = seen_codes.get(code, 0) + 1
    seen_codes[code] = n
    slug = code.lower().replace(".", "-") + (f"-{n}" if n > 1 or code == "D.1a" else "")
    im = Image.open(os.path.join(signs_dir, "raw", f"{file}.png")).convert("RGB")
    if file in KEEP_HEIGHT:
        im = im.crop((0, 0, im.width, int(im.height * KEEP_HEIGHT[file])))
    elif code[0] != "M":  # road markings carry no printed code
        im = crop_label(im)
    im.thumbnail((360, 360))
    im.save(os.path.join(dest_media, f"{slug}.webp"), "WEBP", quality=88, method=6)
    out.append({
        "id": slug,
        "code": code,
        "category": cat_by_letter[code[0]],
        "name": name,
        "description": desc,
        "image": f"{slug}.webp",
    })

data = {
    "categories": [{"id": c[0], "name": c[1], "description": c[2], "letter": c[3]} for c in CATEGORIES],
    "signs": out,
}
json.dump(data, open(dest_json, "w"), ensure_ascii=False, indent=1)
print("signs", len(out))
