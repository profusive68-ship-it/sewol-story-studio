"""API 키가 없거나 대본 생성이 실패했을 때 쓰는 예시 대본 생성기.

Gemini 없이도 '대본 → 이미지 요청서 → 영상' 전체 흐름을 끝까지 확인할 수 있게
장르별 뼈대 이야기를 내장한다. (화면에는 '예시 대본'으로 표시된다)
"""
from __future__ import annotations

from .settings import GENRES

# 각 장르: 인물 / 도입 이미지 / 비트 목록
# 비트 = (화자, 대사, 감정, 효과음 리스트, 영어 이미지 프롬프트, 한국어 장면 설명)
STORIES: dict[str, dict] = {
    "tear_family": {
        "title": "엄마의 마지막 김치통",
        "characters": [
            {"id": "mother", "name": "어머니",
             "desc_en": "Korean grandmother in her late 70s, silver hair in a low bun, faded floral apron, gentle tired eyes"},
            {"id": "son", "name": "아들 정호",
             "desc_en": "Korean man in his late 40s, short graying hair, worn navy jacket, weary face"},
        ],
        "beats": [
            ("narrator", "정호는 어머니가 돌아가신 뒤 삼 년 만에 그 집 문을 열었습니다.", "heal", ["문 삐걱"],
             "A middle-aged Korean man standing at the doorway of an old empty Korean house at dusk, dust in the air, warm fading light",
             "삼 년 만에 문을 연 낡은 집, 문틈으로 먼지가 흐른다"),
            ("narrator", "집 안은 그대로였습니다. 다만 모든 물건 위에 하얀 먼지가 앉아 있었습니다.", "heal", [],
             "Interior of an old Korean home covered in white dust sheets, afternoon light through paper windows, empty and still",
             "세월이 덮인 살림살이, 오후 빛만 남아 있다"),
            ("narrator", "부엌 한쪽, 냉장고 옆에 그 김치통이 있었습니다.", "heal", ["냉장고 웅웅"],
             "A large old brown ceramic kimchi pot in the corner of a Korean kitchen, dust on the lid, cold light from a window",
             "부엌 구석 냉장고 옆, 오래된 갈색 김치통"),
            ("son", "어머니, 이건 왜 아직도 안 버리고 두셨어요.", "conflict", ["한숨"],
             "A middle-aged Korean man crouching in front of an old kimchi pot, hand on the lid, eyebrows drawn together",
             "김치통 뚜껑에 손을 얹은 아들, 표정이 굳는다"),
            ("narrator", "뚜껑을 여는 순간, 정호는 그만 손을 멈추고 말았습니다.", "twist", ["뚜껑 열림", "심장박동"],
             "Closeup of an old kimchi pot opening, revealing a small bundle wrapped in cloth inside, dramatic dim light",
             "뚜껑을 열자 안쪽에 정성껏 싼 보퉁이가 모습을 드러낸다"),
            ("narrator", "김치 대신, 비닐봉지에 겹겹이 싸인 봉투가 가지런히 놓여 있었습니다.", "twist", [],
             "A small cloth-wrapped bundle and stacked envelopes inside an old kimchi pot, extreme closeup, soft light",
             "김치 대신 겹겹이 싸인 봉투가 가지런히 놓여 있다"),
            ("narrator", "봉투마다 날짜가 적혀 있었습니다. 이십 년 전부터 시작된 날짜였습니다.", "twist", [],
             "Stack of old envelopes with handwritten Korean dates, closeup, yellowed paper",
             "봉투마다 적힌 날짜, 이십 년 전부터 시작된 편지"),
            ("son", "이게… 뭐야. 엄마가 이걸 왜.", "conflict", ["종이 바스락"],
             "A middle-aged man holding an old envelope with trembling hands, face lit by a single lamp",
             "봉투를 든 아들의 손이 조금 떨린다"),
            ("narrator", "편지에는 매달 오천 원씩, 정호의 이름으로 적금을 들어 준 기록이었습니다.", "twist", ["심장박동"],
             "Handwritten savings passbook pages spread on a wooden table, old Korean bank stamps, warm lamp light",
             "어머니가 매달 넣어 둔 아들 이름의 적금 기록"),
            ("narrator", "정호가 회사를 그만두겠다고 했던 그 달에도, 어머니는 오천 원을 넣었습니다.", "twist", [],
             "A savings passbook with a deposit slip dated years ago, closeup, dusty table",
             "실직하던 달에도 빠지지 않은 오천 원"),
            ("son", "나 그때… 엄마한테 돈 달라고 한 번도 안 했는데.", "conflict", ["한숨"],
             "Closeup of a man's face holding back tears, dim living room, old family photo blurred behind",
             "말없이 넣어 둔 어머니의 마음"),
            ("narrator", "마지막 봉투에는 김치통 안쪽에 붙여 둔 쪽지가 함께 들어 있었습니다.", "heal", ["종이 바스락"],
             "A handwritten note and a small key inside an envelope, top-down view on a wooden table, warm light",
             "마지막 봉투에 동봉된 짧은 쪽지와 작은 열쇠"),
            ("mother", "정호야. 엄마가 밥을 못 챙겨 줄 때는, 이 김치통을 열어라.", "heal", ["한숨"],
             "An elderly Korean woman's handwriting on a note, closeup, tear stains, warm lamp",
             "김치통 안쪽에 붙여 둔 어머니의 쪽지"),
            ("mother", "엄마는 늘 네 뒤에서 같이 살고 있었단다.", "heal", [],
             "Faded family photograph of a mother and son in a small Korean yard, sunlight, soft focus",
             "오래된 가족사진 속, 아들 뒤에 서 있는 어머니"),
            ("narrator", "정호는 그 자리에 한참을 앉아 있었습니다. 김치통을 끌어안은 채로.", "heal", ["심장박동"],
             "A middle-aged man sitting on the kitchen floor hugging an old kimchi pot, evening light through the window",
             "김치통을 끌어안은 채 부엌에 앉아 있는 아들"),
            ("narrator", "그날 저녁, 정호는 처음으로 혼자 김치를 담갔습니다. 어머니처럼, 소매를 걷고.", "heal", ["찻잔"],
             "A middle-aged man in an apron salting cabbage in a large bowl in a Korean kitchen, warm evening light",
             "어머니처럼 소매를 걷고 담그는 첫 김치"),
            ("narrator", "그리고 그 김치통은, 이제 아들의 집 부엌으로 옮겨졌습니다.", "heal", [],
             "The old brown kimchi pot placed in a clean modern kitchen, morning sunlight, hopeful mood",
             "아들의 부엌으로 옮겨진 어머니의 김치통"),
        ],
    },
    "reversal": {
        "title": "며느리인 줄 알았더니",
        "characters": [
            {"id": "wife", "name": "며느리 수진",
             "desc_en": "Korean woman in her late 30s, dark hair tied back, plain cardigan, calm determined eyes"},
            {"id": "mil", "name": "시어머니",
             "desc_en": "Korean woman in her late 60s, permed short hair, expensive brown coat, sharp gaze"},
            {"id": "husband", "name": "남편 성태",
             "desc_en": "Korean man in his early 40s, office shirt, tired and evasive expression"},
        ],
        "beats": [
            ("narrator", "수진이 시집에 들어온 지 십 년, 그 집 부엌은 늘 수진의 자리였습니다.", "conflict", ["찻잔"],
             "A Korean woman in her thirties washing dishes alone in a large kitchen at night, warm but dim light",
             "밤늦도록 혼자 설거지를 하는 며느리"),
            ("mil", "물은 왜 이렇게 아껴. 그거 아껴서 뭐 하게.", "conflict", ["문 쾅"],
             "An older Korean woman in a brown coat standing in a kitchen doorway with a sharp expression, evening light",
             "부엌문을 열고 들어서는 시어머니의 날카로운 눈빛"),
            ("narrator", "십 년 동안 수진은 한 번도 크게 말하지 않았습니다.", "conflict", [],
             "A woman looking down at a kitchen sink, hands in water, shadowed face, quiet sadness",
             "고개를 숙인 채 말을 삼키는 며느리"),
            ("husband", "수진아, 엄마 말이 좀 세도 너가 이해해 줘.", "conflict", ["한숨"],
             "A man in an office shirt sitting on a sofa avoiding eye contact, late evening living room",
             "고개를 돌린 채 이해를 구하는 남편"),
            ("narrator", "그날, 시어머니가 식탁에 서류를 던졌습니다.", "twist", ["종이 바스락"],
             "A thin document envelope thrown onto a dining table, harsh overhead light, closeup",
             "식탁 위로 던져진 서류 봉투"),
            ("mil", "이혼해. 우리 집에 너 같은 사람 필요 없어.", "conflict", ["문 쿵"],
             "An older Korean woman pointing at divorce papers on a table, cold bright light, dominant posture",
             "이혼하라며 서류를 미는 시어머니"),
            ("narrator", "수진은 화를 내지 않았습니다. 대신 가방에서 서류 한 장을 꺼냈습니다.", "twist", ["심장박동"],
             "A woman calmly placing a single document on the table, closeup of hands, dramatic light",
             "조용히 가방에서 서류 한 장을 꺼내는 수진"),
            ("narrator", "그것은 이 집 건물의 등기부등본이었습니다.", "twist", [],
             "A Korean property registration document on a table, red seal visible, closeup, cold light",
             "건물주 이름이 적힌 등기부등본"),
            ("mil", "이게… 이게 왜 네 이름이야.", "twist", ["찻잔"],
             "An older woman staring at a document, face frozen, harsh light, closeup",
             "서류를 든 시어머니의 얼굴이 굳는다"),
            ("narrator", "수진의 어머니가, 이 집 건물주였습니다. 십 년 전에 조용히 사들인 건물이었습니다.", "twist", [],
             "Aerial view of an old Korean commercial building at dusk, neon signs, cinematic",
             "십 년 전 조용히 사들인, 이 집 건물"),
            ("wife", "십 년 동안 감사했습니다. 이제는 제가 나갈 차례네요.", "heal", ["발자국"],
             "A woman standing up with a small bag over her shoulder, calm face, dawn light through a window",
             "가방을 메고 조용히 일어서는 수진"),
            ("narrator", "수진은 그 집을 나왔습니다. 뒤도 돌아보지 않고.", "heal", ["발자국"],
             "A woman walking out of a Korean house gate at dawn, long shadow, quiet street",
             "뒤도 돌아보지 않고 집을 나서는 수진"),
            ("narrator", "일주일 뒤, 그 집 앞에는 임대료 고지서가 붙었습니다.", "twist", ["종이 바스락"],
             "A rent notice posted on a Korean house gate, closeup, morning light",
             "일주일 뒤 집 대문에 붙은 임대료 고지서"),
            ("narrator", "수진은 그 돈으로 조그만 김밥집을 열었습니다. 자기 이름을 건 가게였습니다.", "heal", [],
             "A small warm Korean kimbap restaurant at night, a woman in an apron smiling behind the counter",
             "자기 이름을 건 작은 김밥집을 연 수진"),
            ("narrator", "그 가게는 삼 년 뒤, 그 동네에서 가장 붐비는 집이 되었습니다.", "heal", ["찻잔"],
             "Busy small Korean restaurant with people waiting outside, warm evening light, hopeful mood",
             "삼 년 뒤 동네에서 가장 붐비는 가게"),
        ],
    },
    "mystery": {
        "title": "매주 오는 택배 상자",
        "characters": [
            {"id": "woman", "name": "지연",
             "desc_en": "Korean woman in her early 50s, short bob hair, beige knit sweater, thoughtful eyes"},
            {"id": "old", "name": "노인",
             "desc_en": "Korean man in his 80s, deep wrinkles, gray flat cap, worn wool coat"},
        ],
        "beats": [
            ("narrator", "지연의 집에는 매주 화요일, 발신인 없는 택배가 도착했습니다.", "conflict", ["문 삐걱"],
             "A small brown parcel on the doorstep of a Korean apartment, early morning light, no sender label",
             "발신인 없는 택배가 놓인 현관"),
            ("narrator", "상자 안에는 늘 낡은 사진 한 장이 들어 있었습니다.", "twist", ["종이 바스락"],
             "An old black-and-white photograph lying inside an open cardboard box, closeup, soft light",
             "상자 안에 든 낡은 흑백사진 한 장"),
            ("woman", "이 사람… 우리 엄마잖아.", "twist", ["심장박동"],
             "A woman holding an old photograph of a young Korean woman, trembling hand, dim living room",
             "사진 속 젊은 여자를 알아본 지연"),
            ("narrator", "사진 속 여자는 스무 살의 어머니였습니다. 지연은 그 사진을 본 적이 없었습니다.", "twist", [],
             "Closeup of a black-and-white photo of a young Korean woman in a 1970s dress, faded edges",
             "스무 살 어머니의 사진, 처음 보는 얼굴"),
            ("narrator", "상자 바닥에는 늘 같은 문장이 적혀 있었습니다. 미안하다고.", "conflict", [],
             "Handwritten Korean words on the bottom of a cardboard box, closeup, dim light",
             "상자 바닥에 적힌 한 문장, 미안하다고"),
            ("narrator", "지연은 택배 회사에 물었지만, 발신인은 끝내 나오지 않았습니다.", "conflict", ["전화벨"],
             "A woman on the phone in a dim kitchen at night, worried expression, phone light on her face",
             "택배 회사에 문의하는 지연, 돌아오는 대답은 없었다"),
            ("narrator", "석 달째 되던 화요일, 상자 안에 처음으로 주소가 들어 있었습니다.", "twist", [],
             "A small handwritten address note inside a box, closeup, morning light",
             "석 달 만에 처음 들어 있던 주소 한 줄"),
            ("narrator", "그 주소는, 어머니가 돌아가시기 전 마지막으로 살던 요양원이었습니다.", "twist", ["심장박동"],
             "An old rural nursing home building in winter, bare trees, gray sky, cinematic wide shot",
             "어머니가 마지막으로 계셨던 요양원"),
            ("old", "네가… 그 집 딸이구나. 눈이 똑같아.", "twist", ["한숨"],
             "An elderly Korean man in a flat cap standing at a nursing home door, emotional eyes, winter light",
             "요양원 문 앞에서 지연을 알아보는 노인"),
            ("narrator", "노인은 사십 년 전, 어머니의 첫사랑이었습니다.", "twist", [],
             "Faded 1980s photograph of a young Korean couple in a rural market, nostalgic tone",
             "사십 년 전, 어머니의 첫사랑"),
            ("old", "내가 못 지켜 줬어. 그 말을 평생 못 했어.", "conflict", ["한숨"],
             "An old man sitting on a bench, hands folded, winter sunlight through a window",
             "평생 못다 한 말을 꺼내는 노인"),
            ("narrator", "어머니는 돌아가시기 전, 그에게 사진을 맡겼습니다. 딸에게 꼭 전해 달라고.", "heal", [],
             "A stack of old photographs tied with a ribbon on a wooden table, warm winter light",
             "딸에게 전해 달라 맡겨 둔 사진들"),
            ("narrator", "지연은 그날 처음으로, 어머니의 젊은 날을 알게 되었습니다.", "heal", ["찻잔"],
             "A woman and an old man looking at photographs together at a small table, warm lamp",
             "노인과 마주 앉아 사진을 넘기는 지연"),
            ("old", "다음 화요일에도… 상자 하나 보내도 될까.", "heal", ["한숨"],
             "An elderly man holding a small cardboard box, hopeful eyes, soft afternoon light",
             "다음 화요일에도 상자를 보내도 되냐는 노인"),
            ("narrator", "그 뒤로 지연의 집에는 매주 화요일, 두 사람의 사진이 도착합니다.", "heal", [],
             "Two old photographs side by side on a sunny table, warm morning light, hopeful",
             "매주 화요일, 이제는 두 사람의 사진이 온다"),
        ],
    },
    "inlaw": {
        "title": "시어머니의 유언장",
        "characters": [
            {"id": "wife", "name": "며느리 미경",
             "desc_en": "Korean woman in her late 40s, shoulder-length hair, simple gray sweater, tired kind face"},
            {"id": "mil", "name": "시어머니",
             "desc_en": "Korean woman in her late 70s, white hair, thin frame, sharp but tired eyes"},
            {"id": "sister", "name": "시누이",
             "desc_en": "Korean woman in her early 50s, heavy makeup, expensive handbag, impatient expression"},
        ],
        "beats": [
            ("narrator", "미경은 시어머니와 이십 년을 함께 살았습니다.", "conflict", ["찻잔"],
             "A Korean woman in her forties setting a table for an elderly woman in a small apartment, evening light",
             "이십 년을 함께 산 며느리와 시어머니의 저녁상"),
            ("mil", "국이 짜다. 너는 늘 손맛이 그 모양이야.", "conflict", ["숟가락"],
             "An elderly Korean woman pushing a soup bowl away at a table, displeased expression, dim light",
             "국이 짜다며 그릇을 미는 시어머니"),
            ("narrator", "미경은 아무 말 없이 물을 한 컵 따라 드렸습니다.", "conflict", [],
             "A woman quietly placing a glass of water in front of an elderly woman, closeup of hands",
             "말없이 물 한 컵을 따라 드리는 며느리"),
            ("sister", "오빠는 왜 이런 것도 못 챙겨. 엄마가 얼마나 속상하시게.", "conflict", ["한숨"],
             "A woman in a expensive coat standing in a small apartment living room, complaining, harsh light",
             "명절마다 나타나 잔소리를 늘어놓는 시누이"),
            ("narrator", "시어머니가 쓰러진 것은, 그해 겨울이었습니다.", "twist", ["심장박동"],
             "An elderly woman lying on the floor of a Korean apartment at night, dramatic light, blurred motion",
             "그해 겨울, 쓰러진 시어머니"),
            ("narrator", "병원비를 두고 시누이는 말했습니다. 나는 형편이 안 된다고.", "conflict", [],
             "A hospital corridor at night, two women arguing in the distance, cold fluorescent light",
             "병원비 앞에서 발을 빼는 시누이"),
            ("narrator", "미경은 십 년 전부터 모아 둔 돈을 꺼냈습니다. 한 번도 말하지 않은 돈이었습니다.", "heal", ["종이 바스락"],
             "A woman opening an old bankbook at a hospital cafeteria table, closeup, tired hands",
             "십 년 동안 모아 둔 통장을 꺼내는 미경"),
            ("mil", "너… 그 돈 어디서 났어.", "twist", ["한숨"],
             "An elderly woman in a hospital bed looking at her daughter-in-law, weak but alert eyes",
             "병상에서 며느리를 바라보는 시어머니"),
            ("wife", "제가 조금씩 모았어요. 어머니 드시는 약값은 제가 하겠습니다.", "heal", [],
             "A woman sitting beside a hospital bed holding an elderly woman's hand, dawn light",
             "병상 옆에서 손을 잡은 며느리"),
            ("narrator", "시어머니는 그날 밤, 오래전에 써 둔 유언장을 간호사에게 맡겼습니다.", "twist", [],
             "A sealed white envelope handed to a nurse in a dim hospital room, closeup, quiet mood",
             "간호사에게 맡긴 봉인된 유언장"),
            ("narrator", "장례가 끝난 뒤, 가족들이 모인 자리에서 유언장이 열렸습니다.", "conflict", ["종이 바스락"],
             "A family gathered around a table in a Korean apartment, a lawyer opening a document, tense light",
             "가족이 모인 자리에서 열린 유언장"),
            ("sister", "엄마가 왜… 왜 미경 씨한테 집을 준다는 거야.", "twist", ["심장박동"],
             "A woman standing up from a table in shock, legal document in hand, harsh indoor light",
             "유언장을 든 시누이가 자리에서 일어난다"),
            ("narrator", "유언장에는 이렇게 적혀 있었습니다. 이십 년 동안 내 밥을 챙긴 사람에게.", "heal", [],
             "Closeup of a Korean handwritten will on old paper, warm lamp light, tear-blurred",
             "이십 년 동안 밥을 챙긴 사람에게"),
            ("narrator", "미경은 그 집을 팔지 않았습니다. 대신 시어머니 방을 그대로 두었습니다.", "heal", [],
             "A small Korean apartment room kept tidy with an old woman's belongings, morning light",
             "시어머니 방을 그대로 남겨 둔 미경"),
            ("narrator", "매일 아침, 그 방 문을 열어 인사를 합니다. 어머니, 아침입니다.", "heal", ["문 삐걱"],
             "A woman opening a door to a sunlit empty room with a small portrait on the dresser",
             "매일 아침 그 방 문을 열어 인사하는 며느리"),
        ],
    },
    "free": {
        "title": "그날의 편지",
        "characters": [
            {"id": "lead", "name": "주인공",
             "desc_en": "Korean woman in her late 40s, short hair, plain coat, thoughtful face"},
            {"id": "other", "name": "상대",
             "desc_en": "Korean man in his early 50s, gray jacket, weathered kind face"},
        ],
        "beats": [
            ("narrator", "그날, 주인공의 책상 위에 오래된 편지 한 장이 놓여 있었습니다.", "conflict", ["종이 바스락"],
             "A single old letter on a wooden desk, late afternoon light, dust in the air",
             "책상 위에 놓인 오래된 편지 한 장"),
            ("narrator", "봉투에는 주소도, 이름도 없었습니다.", "twist", [],
             "An unaddressed old envelope, closeup, yellowed paper, soft window light",
             "주소도 이름도 없는 봉투"),
            ("lead", "이걸… 누가 두고 간 거지.", "conflict", ["한숨"],
             "A woman holding an old envelope, looking around an empty office, dim light",
             "빈 사무실에서 봉투를 든 주인공"),
            ("narrator", "편지 안에는 짧은 문장 하나가 적혀 있었습니다. 미안하다는 말이었습니다.", "twist", ["심장박동"],
             "Handwritten Korean sentence on old letter paper, closeup, warm lamp light",
             "편지 안의 짧은 문장, 미안하다는 말"),
            ("narrator", "주인공은 그 문장을 오래 바라보았습니다.", "heal", [],
             "A woman sitting by a window at dusk, letter in hand, city lights blurred outside",
             "창가에 앉아 편지를 오래 바라보는 시간"),
            ("other", "그 편지, 내가 쓴 거야.", "twist", ["발자국"],
             "A man in a gray jacket standing in a doorway, hesitant posture, evening light",
             "문가에 서서 말을 꺼내는 남자"),
            ("narrator", "이십 년 전, 두 사람은 같은 골목에서 살았습니다.", "heal", [],
             "A narrow Korean alley in the 1990s, warm streetlight, old shops, nostalgic tone",
             "이십 년 전 두 사람이 살던 골목"),
            ("lead", "그때 왜 아무 말도 안 했어요.", "conflict", ["한숨"],
             "A woman looking up at a man, eyes full of old questions, warm lamplight",
             "이십 년 묵은 물음을 꺼내는 주인공"),
            ("other", "말하면 네가 힘들어질까 봐. 그뿐이었어.", "conflict", [],
             "A man looking down, hands in pockets, soft evening light, quiet sadness",
             "말을 삼켰던 이유를 꺼내는 남자"),
            ("narrator", "두 사람은 그날 밤, 골목 끝 포장마차에 마주 앉았습니다.", "heal", ["찻잔"],
             "Two people sitting at a small Korean street tent bar at night, warm lamps, steam rising",
             "골목 끝 포장마차에 마주 앉은 두 사람"),
            ("narrator", "이십 년 동안 하지 못한 말들이, 그제야 하나씩 나왔습니다.", "heal", [],
             "Closeup of two cups of tea on a wooden table, steam, warm light, intimate mood",
             "이십 년 만에 하나씩 꺼내는 이야기"),
            ("other", "이제라도… 자주 보고 싶어.", "heal", ["한숨"],
             "A man smiling faintly at a woman across a small table, warm light, hopeful mood",
             "이제라도 자주 보고 싶다는 말"),
            ("narrator", "주인공은 대답 대신 고개를 끄덕였습니다.", "heal", [],
             "A woman nodding slightly, eyes glistening, warm streetlight, closeup",
             "대답 대신 조용히 고개를 끄덕이는 주인공"),
            ("narrator", "그날의 편지는, 이십 년 만에 제자리를 찾았습니다.", "heal", [],
             "An old letter placed carefully inside a drawer beside a family photo, morning light",
             "이십 년 만에 제자리를 찾은 편지"),
        ],
    },
}

FILLERS = {
    "tear_family": [
        ("narrator", "창밖에서는 바람이 불었습니다. 집 안의 시계 소리만 크게 들렸습니다.", "heal",
         "Wind moving a curtain in an old Korean house, clock on the wall, quiet afternoon light",
         "바람이 스치는 오후, 시계 소리만 또렷하다"),
        ("narrator", "정호는 어머니의 손버릇을 떠올렸습니다. 국을 끓일 때면 늘 뚜껑을 반쯤 열어 두셨습니다.", "heal",
         "An old pot with the lid half open in a Korean kitchen, steam, warm light",
         "뚜껑을 반쯤 열어 두던 어머니의 손버릇"),
        ("son", "어머니, 저 잘 지내요. 정말로.", "heal",
         "A middle-aged man standing alone in a kitchen talking to no one, evening light",
         "아무도 없는 부엌에서 혼잣말을 하는 아들"),
    ],
    "reversal": [
        ("narrator", "수진은 그날의 일을 오래 기억했습니다. 창피해서가 아니라, 다행이라서였습니다.", "heal",
         "A woman looking out of a small restaurant window at night, soft reflection",
         "창밖을 보는 수진의 눈에 비친 불빛"),
        ("narrator", "그 집 식구들은 그 뒤로도 가끔 가게 앞을 지나갔습니다.", "conflict",
         "An elderly woman and a man walking past a small restaurant at night, hesitant glances",
         "가게 앞을 지나며 안을 들여다보는 사람들"),
        ("wife", "어서 오세요. 오늘 김밥 맛있어요.", "heal",
         "A woman in an apron smiling behind a counter, warm restaurant light, evening",
         "웃으며 손님을 맞는 수진"),
    ],
    "mystery": [
        ("narrator", "지연은 그 사진들을 한 장씩 넘겨 보았습니다. 모르는 얼굴이었지만 낯설지 않았습니다.", "heal",
         "A woman looking through old photographs at a wooden table, warm lamp, quiet mood",
         "한 장씩 넘겨 보는 오래된 사진들"),
        ("narrator", "화요일은 이제 지연에게 기다려지는 요일이 되었습니다.", "heal",
         "A calendar with Tuesdays circled, morning light on a kitchen table, hopeful mood",
         "동그라미가 쳐진 화요일들"),
        ("old", "사진은… 사람이 남기는 마지막 인사더라.", "heal",
         "An elderly man holding a photograph, soft winter light, gentle expression",
         "사진은 마지막 인사라는 노인의 말"),
    ],
    "inlaw": [
        ("narrator", "미경은 그 집 살림을 그대로 두었습니다. 장롱 위 꽃무늬 이불까지도.", "heal",
         "An old Korean bedroom with a floral blanket folded on a dresser, morning light",
         "그대로 남겨 둔 장롱 위 이불"),
        ("narrator", "시누이는 그 뒤로 자주 오지 않았습니다. 미경은 그것도 조용히 받아들였습니다.", "heal",
         "A quiet Korean apartment living room, single teacup on the table, afternoon light",
         "조용해진 거실, 혼자 놓인 찻잔"),
        ("wife", "어머니, 오늘은 국을 조금 싱겁게 끓였어요.", "heal",
         "A woman placing a bowl of soup on a small table in front of a portrait, warm light",
         "초상 앞에 국 한 그릇을 놓는 며느리"),
    ],
    "free": [
        ("narrator", "그 후로 주인공은 가끔 그 골목을 걸었습니다. 예전과 달라진 것들을 하나씩 세면서.", "heal",
         "A woman walking down a changed Korean alley at dusk, warm streetlights",
         "달라진 골목을 천천히 걷는 주인공"),
        ("narrator", "기억은 사라지지 않았습니다. 다만 조금씩 자리를 옮겼습니다.", "heal",
         "Sunset light falling on an old wooden desk with a single photograph, quiet mood",
         "빛이 옮겨 간 책상 위의 사진 한 장"),
        ("other", "우리, 이제 천천히 가자.", "heal",
         "Two people walking side by side on a quiet Korean street at dusk, long shadows",
         "나란히 걷는 두 사람의 긴 그림자"),
    ],
}

CHAPTER_TITLES = {
    "tear_family": ["삼 년 만에 연 문", "먼지 앉은 부엌", "김치통", "겹겹이 싼 봉투",
                    "이십 년의 날짜", "말하지 않은 돈", "마지막 쪽지", "혼자 담근 김치"],
    "reversal": ["십 년의 부엌", "던져진 서류", "등기부등본", "나가는 문",
                 "임대료 고지서", "작은 김밥집", "삼 년 뒤", "다시 선 자리"],
    "mystery": ["화요일의 택배", "낡은 사진", "미안하다는 문장", "주소 한 줄",
                "요양원", "사십 년 전", "맡겨 둔 사진", "기다려지는 화요일"],
    "inlaw": ["이십 년의 밥상", "짜다는 말", "겨울의 쓰러짐", "병원비",
              "모아 둔 통장", "유언장", "남겨 둔 방", "아침 인사"],
    "free": ["책상 위의 편지", "이름 없는 봉투", "미안하다는 말", "이십 년 전 골목",
             "포장마차", "꺼내는 말들", "제자리", "천천히 가는 길"],
}


# 장르별 후속편 떡밥(6개월 뒤) / 다음 사연 추천
TEASERS = {
    "tear_family": {
        "six_months": "육 개월 뒤, 정호의 부엌에 다시 그 김치통이 놓였습니다. 이번에는 아들이 처음 담근 김치가 익어 가고 있었습니다.",
        "next_title": "아버지의 낡은 손목시계",
        "next_teaser": "다음 사연은, 돌아가신 아버지의 손목시계가 매일 두 분씩 늦어지는 이유에 대한 이야기입니다.",
    },
    "reversal": {
        "six_months": "육 개월 뒤, 그 집 대문 앞에 수진의 김밥집 두 번째 간판이 걸렸습니다. 이번에는 시어머니가 그 앞에서 서성이고 있었습니다.",
        "next_title": "사장님의 마지막 지시",
        "next_teaser": "다음 사연은, 퇴사 통보를 받은 날 회사 금고에서 이상한 봉투를 발견한 사람의 이야기입니다.",
    },
    "mystery": {
        "six_months": "육 개월 뒤, 화요일의 택배 상자 안에는 사진 대신 작은 열쇠 하나가 들어 있었습니다. 그 열쇠는 지연의 어머니가 남긴 금고의 것이었습니다.",
        "next_title": "이름 없는 묘비",
        "next_teaser": "다음 사연은, 아무도 찾지 않는 산기슭 묘비에 매년 국화꽃이 놓이는 이유에 대한 이야기입니다.",
    },
    "inlaw": {
        "six_months": "육 개월 뒤, 미경의 집 문 앞에 시누이가 작은 상자를 들고 서 있었습니다. 상자 안에는 시어머니가 남긴 편지가 들어 있었습니다.",
        "next_title": "며느리의 장바구니",
        "next_teaser": "다음 사연은, 매일 같은 시장 같은 가게만 찾는 며느리의 장바구니 속 비밀에 대한 이야기입니다.",
    },
    "free": {
        "six_months": "육 개월 뒤, 그 골목 끝에는 작은 편지함이 하나 생겼습니다. 두 사람은 그 안에 매주 짧은 쪽지를 넣어 두기로 했습니다.",
        "next_title": "그 골목의 봄",
        "next_teaser": "다음 사연은, 이십 년 만에 다시 만난 두 사람의 다음 계절에 대한 이야기입니다.",
    },
}


TITLE_PATTERNS = {
    "tear_family": ["{t} — 어머니가 남긴 마지막 한마디", "버리라던 김치통, 20년 뒤 열어보니", "아들이 끝내 몰랐던 어머니의 20년"],
    "reversal": ["{t} — 십 년 참은 며느리의 한 장", "이혼하라던 시어머니, 등기부등본 보고 얼어붙다", "시집에서 쫓겨난 날, 그 집 건물주가 바뀌었다"],
    "mystery": ["{t} — 매주 화요일 오는 발신인 없는 택배", "사진 한 장씩 오던 택배, 마지막 상자에 담긴 것", "어머니가 숨긴 사십 년 전 사진의 주인"],
    "inlaw": ["{t} — 이십 년 밥상의 대가", "유언장에 적힌 한 줄, '밥 챙긴 사람에게'", "병원비 앞에서 발 뺀 시누이, 유언장 보고 울었다"],
    "free": ["{t} — 이십 년 만에 도착한 편지", "주소도 이름도 없는 편지 한 장", "그날의 편지가 이십 년 만에 제자리를 찾았다"],
}
HASHTAGS = {
    "tear_family": ["#사연", "#감동사연", "#가족사연", "#라디오드라마", "#어머니", "#눈물", "#시니어", "#노인사연", "#실화같은이야기", "#세월의사연극장"],
    "reversal": ["#사연", "#사이다", "#반전", "#며느리", "#라디오드라마", "#시니어", "#가족사연", "#통쾌한이야기", "#실화같은이야기", "#세월의사연극장"],
    "mystery": ["#사연", "#미스터리", "#반전", "#라디오드라마", "#가족사연", "#시니어", "#노인사연", "#실화같은이야기", "#사진", "#세월의사연극장"],
    "inlaw": ["#사연", "#시댁", "#며느리", "#유언장", "#라디오드라마", "#가족사연", "#시니어", "#감동사연", "#실화같은이야기", "#세월의사연극장"],
    "free": ["#사연", "#라디오드라마", "#감동사연", "#편지", "#시니어", "#노인사연", "#실화같은이야기", "#이야기", "#세월의사연극장", "#사연제보"],
}


def _est_chars(target_sec: float) -> int:
    return int(target_sec * 4.3)


def build_template_script(settings: dict) -> dict:
    """settings: genre, topic, target_seconds, hook15, sequel, title_hint ..."""
    genre = settings.get("genre", "tear_family")
    if genre not in STORIES:
        genre = "free"
    story = STORIES[genre]
    target = float(settings.get("target_seconds") or 300)
    topic = (settings.get("topic") or "").strip()

    beats = list(story["beats"])
    fillers = FILLERS.get(genre, [])
    need = _est_chars(target)
    have = sum(len(b[1]) for b in beats)
    rounds = 0
    expanded = list(beats)
    # 부족하면 중간에 여백 비트를 끼워 넣어 길이를 늘린다 (예시 대본 한정)
    while have < need * 0.92 and rounds < 40 and fillers:
        insert_at = min(len(expanded) - 2, 3 + rounds * 2)
        filler = fillers[rounds % len(fillers)]
        expanded.insert(max(1, insert_at), filler)
        have += len(filler[1])
        rounds += 1

    # 50초 쇼츠는 핵심 비트만 남긴다
    if target <= 90:
        def _first(pred):
            for b in expanded:
                if pred(b):
                    return b
            return None
        picks = []
        for pred in (lambda b: b[2] == "heal", lambda b: b[2] == "conflict",
                     lambda b: b[2] == "twist", lambda b: b[2] == "heal"):
            b = _first(pred)
            if b and b not in picks:
                picks.append(b)
        if expanded[-1] not in picks:
            picks.append(expanded[-1])
        expanded = picks[:5]

    # ── 콜드 오픈: 0초에 가장 충격적인 절정 한 줄을 먼저 놓고, 되감기 자막 뒤 본론으로 ──
    twist_beats = [b for b in expanded if b[2] == "twist"] or expanded[-2:]
    hook_beats = twist_beats[-3:]
    hook_scenes = []
    for speaker, text, _emo, sfx, en, ko in hook_beats:
        line = _first_sentence(text)
        hook_scenes.append({
            "speaker": speaker, "text": line, "emotion": "twist", "sfx": list(sfx)[:1],
            "image_prompt": en, "image_caption": ko, "hook_line": True,
        })
    # 첫 15초가 되도록 훅 대사를 조금 더 보탠다
    total_hook = sum(len(s["text"]) for s in hook_scenes)
    if total_hook < 52 and len(twist_beats) >= 2:
        extra_speaker, extra_text, _e, extra_sfx, extra_en, extra_ko = twist_beats[-1]
        rest = extra_text.split(".", 1)[-1].strip()
        if rest and rest not in hook_scenes[-1]["text"]:
            hook_scenes.append({"speaker": extra_speaker, "text": rest[:48], "emotion": "twist",
                                "sfx": list(extra_sfx)[:1], "image_prompt": extra_en,
                                "image_caption": extra_ko, "hook_line": True})
    rewind = {
        "speaker": "narrator", "text": "사흘 전, 아무것도 몰랐던 그날.", "emotion": "heal",
        "sfx": [], "image_prompt": hook_scenes[0]["image_prompt"] if hook_scenes else expanded[0][4],
        "image_caption": "되감기 — 그날보다 사흘 전", "placement": "after_hook",
    }

    expanded = [b if len(b) == 6 else (b[0], b[1], b[2], [], b[3], b[4]) for b in expanded]

    scenes = hook_scenes + [rewind]
    for speaker, text, emotion, sfx, en, ko in expanded:
        scenes.append({
            "speaker": speaker, "text": text, "emotion": emotion, "sfx": list(sfx),
            "image_prompt": en, "image_caption": ko,
        })

    n_ch = max(1, min(len(CHAPTER_TITLES.get(genre, [])), max(1, int(target // 180))))
    titles = CHAPTER_TITLES.get(genre, ["이야기"])
    per = max(1, (len(scenes) - len(hook_scenes) - 1) // n_ch)
    for idx, sc in enumerate(scenes):
        if sc.get("hook_line") or idx == len(hook_scenes):
            sc["chapter"] = 1
        else:
            sc["chapter"] = min(n_ch, (idx - len(hook_scenes) - 1) // per + 1)
        sc["id"] = f"s{idx + 1:02d}"
        sc["chapter_title"] = titles[min(n_ch, sc["chapter"]) - 1] if titles else ""

    chapters = [{"index": 1, "title": "훅", "anchor": "s01"}]
    if n_ch > 1:
        chapters.append({"index": 2, "title": titles[0], "anchor": f"s{len(hook_scenes) + 2:02d}"})
    chapters = chapters[:1] if n_ch == 1 else chapters

    title = story["title"]
    if genre == "free" and topic:
        title = topic[:28]

    hook_ids = [sc["id"] for sc in scenes[:len(hook_scenes)]] or [scenes[0]["id"]]
    t = TEASERS.get(genre, TEASERS["free"])
    teaser = t["six_months"] if settings.get("sequel", True) else ""

    pats = TITLE_PATTERNS.get(genre, TITLE_PATTERNS["free"])
    titles = [pat.format(t=title) for pat in pats]
    if title not in titles:
        titles.insert(0, title)
    desc = " · ".join(dict.fromkeys([b[5] for b in expanded[:4]]))
    desc = f"{title}\n\n{desc}\n\n사연은 창작·각색된 이야기입니다."
    return {
        "source": "template",
        "title": title,
        "titles": titles[:3],
        "description": desc,
        "hashtags": HASHTAGS.get(genre, HASHTAGS["free"]),
        "logline": GENRES.get(genre, {}).get("hint", ""),
        "setting": "",
        "characters": story["characters"],
        "evidence": [],
        "acts": [],
        "scenes": scenes,
        "chapters": chapters,
        "hook": {"scene_ids": hook_ids,
                 "caption": scenes[0]["text"][:40] if scenes else "",
                 "line": scenes[0]["text"][:80] if scenes else "",
                 "rewind_caption": "사흘 전, 아무것도 몰랐던 그날"},
        "sequel_teaser": teaser,
        "next_story": {"title": t["next_title"], "teaser": t["next_teaser"]},
        "thumbnail": {
            "style1": [title, "실화 같은 사연"],
            "style2": _style2_lines(scenes, title),
        },
        "upload": {
            "title": title,
            "description": f"{title}\n\n{GENRES.get(genre, {}).get('hint', '')}",
            "tags": ["사연", "라디오드라마", "감동사연", "세월의사연극장", "이야기"],
        },
    }


def _first_sentence(text: str) -> str:
    parts = [p.strip() for p in text.replace("?", ".").replace("!", ".").split(".") if p.strip()]
    if not parts:
        return text[:40]
    line = parts[0] + "."
    if len(line) > 42:
        line = line[:40] + "…"
    return line


def _pick_hook(scenes: list[dict]) -> list[str]:
    """가장 충격적인 절정 장면 1~3개를 고른다 (twist 우선, 뒤쪽 우선)."""
    twist = [s for s in scenes if s["emotion"] == "twist"]
    pool = twist or scenes
    chosen = sorted(pool[-2:], key=lambda s: s["id"])
    # 15초 분량에 맞춰 최대 3개
    ids: list[str] = []
    total = 0
    for s in chosen:
        ids.append(s["id"])
        total += len(s["text"]) / 4.3
        if total >= 13:
            break
    return ids or [scenes[0]["id"]]


def _style2_lines(scenes: list[dict], title: str) -> list[str]:
    picks = []
    for s in scenes:
        t = s["text"].strip()
        if 10 <= len(t) <= 22 and s["emotion"] in ("twist", "heal", "conflict"):
            picks.append("“" + t + "”")
        if len(picks) >= 3:
            break
    lines = picks or ["“그날, 그 말을 했더라면”"]
    lines.insert(0, "“" + title + "”")
    lines.append("마지막까지 보세요")
    return lines[:5]
