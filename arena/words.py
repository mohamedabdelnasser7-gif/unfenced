"""Word lists for arena/clean.py (new, 2026-10-30): common Egyptian first names, the words that
are never a name, and the cue words before a name. Plain lists, read once.

Arabic words are compared after fold() below (أ إ آ as ا, ة as ه, ى as ي), on text whose short
vowels and tatweel arena/clean.py normalize already took out; Latin ones in lower case. So each
list holds one spelling of each word, and the sets at the bottom are built with fold().

FIRST_NAMES  masked wherever they stand, also joined to و, ف, ب, ل or يا (لعمر, يامحمد). Arabic,
             Franco (with 2 3 5 7 8 9) and English spellings.
CUE_NAMES    names that are also everyday words (علي is على once folded, منى is مني "from me",
             نور, امل, فرح, نادر, اسماء, nour as in sabah el nour): masked only after a cue (يا, a
             title, اسمي, a relation word) or right after another name.
STOP         words that are never taken as a name after a cue or after another name: function
             words, common verbs and shop words.
"""

FIRST_NAMES_AR = """
محمد احمد محمود مصطفي عمر عمرو حسن حسين حسام كريم خالد طارق ياسين يوسف ابراهيم اسماعيل عبده سيد
شريف هاني هشام وليد ايمن ايهاب تامر حازم حاتم حامد حمدي حماده رامي رامز سامح سامي سمير شادي ماجد
مجدي مدحت مراد مروان معتز منير ناصر نبيل وايل ياسر يحيي زياد سعد عاطف عصام عماد عمار فادي فارس
فتحي فوزي جلال رافت رشاد صبري صابر طه عاصم عثمان عزت علاء قاسم لوي مازن محسن مختار مهند
مومن هيثم يسري اشرف انس اسامه اكرم انور بلال ثروت جورج جرجس حمزه خليل رووف رءوف رياض زكريا
سليمان شوقي صفوت ضياء فاروق لطفي ماهر متولي بيشوي بولا ابانوب كيرلس مايكل بيتر
اندرو ديفيد ادهم مهاب اياد سيف وسام يونس شهاب سامر طلال نزار صهيب حسني حمو حوده عزوز توفيق حسونه
زكي ممدوح منصور اسلام شنوده بطرس مرقس مرقص يوحنا ماركو كيرو عبدو محمدين حماد سعيد مينا
فاطمه مريم ساره هبه هدي ندي دينا رنا ريم سلمي ليلي ياسمين اسراء بسمه حنان خلود داليا رانيا رضوي
روان ريهام زينب سحر سعاد سلوي سميه شيماء شيرين عبير علا غاده لمياء مها مروه منار ميار نادين
نجلاء نرمين نسمه نهي نهاد هاله هايدي هند يارا جنا رقيه تسنيم اسيل ليان مايا ميرنا مارينا
ماريان مريهان نيره ساندي سالي شهد خديجه ايتن بسنت سهي نورهان هاجر يمني لوجي نوران رودينا سندس شروق
رحاب جني ياسمينا ميرال
"""

FIRST_NAMES_LA = """
mohamed mohammed muhammad mohammad mohamad mo moh mo7amed mo7ammed ahmed ahmad a7med mahmoud
mahmood ma7moud mostafa mustafa moustafa omar 3omar amr 3amr hassan 7assan hasan hussein hossein husein
7ussein 7usein hossam 7ossam hosam karim kareem khaled khalid 5aled tarek tarik tareq yassin yassine
yasin yaseen youssef yousef yusuf youssif ibrahim ebrahim ismail esmail abdo sayed sherif hany hani
hesham hisham walid waleed ayman ehab tamer hazem hatem hamed hamdy hamada 7amada hamo 7amo 7oda
ramy rami ramez sameh samy sami samir shady shadi maged magdy medhat mourad morad marwan moataz mo3taz
mounir nasser nabil wael yasser yaser yehia yahya ziad zeyad saad atef essam emad ammar fady fadi
fares fathy fawzy galal raafat rashad sabry saber taha assem abdallah abdullah
abdelrahman abdulrahman osman ezzat alaa kassem loay mazen mohsen mokhtar mohanad moamen momen haitham
haytham yousry ashraf anas osama usama akram anwar belal bilal george girgis hamza khalil raouf
riad zakaria soliman shawky safwat diaa farouk lotfy maher metwally mina bishoy bola paula
abanoub kirollos michael peter john andrew david adham seif saif wessam younes shehab samer islam
mamdouh mansour fawzi ali adel 3adel saeed sa3eed
fatma fatima mariam maryam sara sarah mona heba hoda dina rana reem salma laila layla leila yasmine
yasmin jasmine asmaa esraa omnia basma hanan kholoud dalia rania radwa
rawan reham zeinab zainab sahar soad salwa samah somaya shaimaa shereen sherine safaa abeer ola ghada
lobna maha marwa manar mayar nadine naglaa nermeen nesma noha nehad haidy heidi hend hind
wafaa yara jana rokaya tasneem aseel layan mirna marina mariane
merhan nayera sally shahd aisha khadija zeina doaa bassant nourhan hagar yomna nouran
yasmina
"""

CUE_NAMES_AR = """
علي مني منه منة نور امل ايه رحمه ايمان سماح صفاء وفاء فرح ملك حبيبه زينه دعاء تقي عادل جميل جمال
كمال صلاح رضا زين امير مالك كامل هادي عزيز رمضان صالح باسم بكر كرم مرسي مي نادر فريد حلمي شكري رمزي
فكري اسماء امنيه عايشه لينا بودي ميدو زيزو جميله كريمه لبني سليم رجب شعبان مجد وجيه عوض
"""

CUE_NAMES_LA = """
may mark body said malak nada menna mena zizo mido reda salah kamal gamal amir zain zein hady hadi aziz
ramadan kamel malek basem karam morsi mai sandy habiba gamila karima nader hala amal eman iman aya lina
lena farah maya nour noor rahma ra7ma selim ragab shaaban wagih
3ali
"""
# 3ali is Franco for "high" too (el se3r 3ali awi): a cue name like علي, never masked on its own.

# Words that are never a name after a cue or another name (folded spellings).
STOP_AR = """
انا انت انتي انتو انتم احنا هو هي هما ده دي دا دول اللي الي في ف من مني منه علي عن مع ل ب و او ولا بس
لو عشان علشان لان يعني طب طيب تمام اوكي ماشي شكرا متشكر ممكن عايز عايزه عاوز عاوزه محتاج محتاجه
عندي عندك عنده عندها عندكم عندنا معايا معاك معاكي معاه معاها هنا هناك كده كدا برضه برده كمان لسه
دلوقتي النهارده بكره امبارح مش ما لا ايوه اه يا ازاي ازيك ازيكم امتي فين ليه كام بكام ايه اي مين
كل حاجه جزمه جزم طقم تيشيرت فانله شوز كوتشي مقاس مقاسه مقاسها مقاسي مقاسك مقاسات لون الوان اسود
ابيض احمر ازرق كحلي رمادي بني اخضر بيج جديد جديده اصلي اصليه كوبي سعر سعرها سعره شحن توصيل دفع كاش
خصم عرض ساكن ساكنه قاعد قاعده رايح جاي نازل مسافر برا بره جوه هاخد هاخده هاخدها هطلب اطلب اكدلي
ابعت ابعتلي ابعتها ابعته ابعتوا ابعتوها ارجوك لوسمحت سمحت حضرتك فندم افندم باشا جميل حلو كويس وحش
غالي غاليه رخيص صغير كبير واسع ضيق سلام عليكم اهلا مرحبا صباح مساء الخير النور خير الحمد لله الله
بتاع بتاعي بتاعتي بتاعه بتاعها رقم رقمي رقمه رقمها ورقمي ورقمه عنوان عنواني اسم اسمي واسمي اسمه
اسمها ابني بنتي ماما بابا اخويا اختي جوزي مراتي صاحبي صاحبتي هديه عيد ميلاد ماتش تمرين نادي ملعب
قال قالي قالت قالتلي قالولي بيقول بتقول عمره عمرها سنه سنين كامل بالكامل الكامل ثلاثي التلاتي
الثلاثي هيستلم هتستلم هستلم استلم المستلم تحت امرك امرك وصل وصلت وصلني موجود موجوده متاح متاحه
مفيش فيه فيها عليه عليها لينا ليكم ليه ليها طلب بعت دفع شاف كلم سال رد عمل جاب خد اخد راح جه كان
مكتب مكتبي مكتبنا شغل شغلي بيت بيتي البيت محل المحل فرع اقرب ايميل ايميلي الايميل بوابه البواب
حبيبي حبيبتي
"""
# Product words beside a name or after one are never a name (round 3 of the feed review, 2026-10-31):
# what a customer asks for, its colour and its model stay readable in every turn.
PRODUCT_AR = """
جاكيت جاكت جواكت هودي جيرسي تيشرت قميص شورت بنطلون شراب شنطه كاب فستان جلد جلدي سودا سوده بيضا بيضه
حمرا زرقا خضرا صفرا اصفر رصاصي ذهبي فضي برتقالي بنفسجي زيتي بمبي نبيتي موف فيبور ميركوريال بريداتور
نايكي نايك اديداس بوما اوريجينال اورجينال اورجنال اوردر
"""

STOP_LA = """
i im i'm me my mine you your he she we they it its it's is am are was were be the a an and or but so
to from in on at of for with by here there this that these those want need would like looking
interested just only also too very ok okay thanks thank please pls plz hi hello hey yes no not size
price boots shoes kit order delivery shipping cash live living sorry sure fine good great waiting going
coming ana enta enti entu e7na howa heya 3ayez 3ayza 3awez 3awza 3ayz ma7tag mesh msh mish fe fi fel
fil f men mn w wala aw bas law 3ashan tab tayeb tamam mashy shokran momken 3andi ma3aya hena keda kda
kaman lessa lsa delwa2ty dlw2ty ya ezay ezayak emta fein fen leh kam bkam eh eih eeh mein el sakn sakna
gay ray7 nazel barra gowa ha5od hatlob otlob akkedly eb3at gazma ma2as lon se3r sha7n khasm sabah masa2
salam ahlan el7amdolelah full name what where when how who which why can could will should do does did
have has had get got send sent call message msg dm thx
work home house office email mail gmail inbox kindly check
"""
PRODUCT_LA = """
jacket jackets hoodie jersey shirt tshirt shorts pants bag cap dress leather waterproof original
black white red blue green grey gray navy beige brown pink yellow orange purple gold silver
nike adidas puma mercurial predator vapor superfly phantom tiempo copa elite pro academy
"""

TITLES_AR = """
استاذ استاذه الاستاذ الاستاذه استاز مدام المدام كابتن الكابتن باشمهندس باشمهندسه بشمهندس مهندس مهندسه
المهندس المهندسه دكتور دكتوره الدكتور الدكتوره حاج حاجه الحاج الحاجه مستر ميس انسه الانسه السيد
السيده سيده عم عمو ابو شيخ الشيخ الاخ الاخت
"""

TITLES_LA = """
mr mrs ms miss mister madam madame captain capt kaptin kabtin coach ostaz ostaza ustaz ustaza dr doctor
eng engineer mohandes mohandesa bashmohandes bashmohandesa hag hagga sheikh sheikha 3am amo abu abo
"""
# Latin titles written in English: the word after them is a name only when it is on a list or
# has a capital letter (Mr Smith, not "the coach said"). The Franco ones take any word that is
# not a stop word (ya ostaz marzouk).
ENGLISH_TITLES = "mr mrs ms miss mister madam madame captain capt coach dr doctor eng engineer"

# Cue words before a name. WEAK: a name follows only when it is on a list or written with a capital
# letter (انا عايز is no name). RELATION: a word that is not a stop word is a name (لابني عمر).
WEAK_AR = "انا معاك معاكي معاكم اهلا اهلين مرحبا هاي هالو شكرا متشكر متشكره ميرسي"
WEAK_LA = "ana i'm im m3ak ma3ak m3aki"
WEAK_PAIRS = (("i", "am"), ("this", "is"), ("it's",), ("its",))
RELATION_AR = """
لابني لبنتي لماما لبابا لاخويا لاختي لجوزي لمراتي لصاحبي لصاحبتي لخالي لعمي لخالتي لعمتي لجدي لجدتي
ابني بنتي اخويا اختي ماما بابا جوزي مراتي صاحبي صاحبتي خالي عمي خالتي عمتي
خطيبتي خطيبي لخطيبتي لخطيبي
"""
RELATION_PAIRS = tuple(("my", w) for w in ("son", "daughter", "brother", "sister", "wife", "husband", "friend",
                                          "mom", "mum", "dad", "mother", "father", "cousin"))
# After these a lower case Latin word that is no stop word is a name too (deliver to zorvex).
DELIVERY_PAIRS = tuple((verb, *mid, "to") for verb in ("deliver", "ship", "send")
                       for mid in ((), ("it",), ("them",)))
DETACHED = ("ل",)  # ل or لـ written apart from the name: ابعتها لـ كريم
# Before these a ل joined to a name-like word is a name too (ابعتها لزوزو, وصلها لزوزو).
DELIVERY_VERBS = frozenset("""ابعتها ابعتوها ابعته ابعتوه ابعتيها وصلها وصلوها وصله وصلوه هاتها هاته سلمها سلمه
سلموها سلموه""".split())
# Names a weak cue or a lone ل never takes: they are everyday words once folded (على, منى, منه, ايه).
NOT_AFTER_WEAK = ("علي", "مني", "منه", "ايه", "لينا", "عند")

# ---- the sets clean.py reads, every word folded

_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ؤ": "و", "ئ": "ي", "ة": "ه", "ى": "ي",
                       "’": "'", "‘": "'"})


def fold(word):
    """A word as the lists hold it: one alef, ه for ة, ي for ى, lower case, a plain apostrophe."""
    return str(word).translate(_FOLD).casefold()


def _set(*texts):
    return frozenset(fold(w) for t in texts for w in t.split())


FIRST = _set(FIRST_NAMES_AR, FIRST_NAMES_LA)
CUE = _set(CUE_NAMES_AR, CUE_NAMES_LA) - FIRST
STOP = _set(STOP_AR, STOP_LA, PRODUCT_AR, PRODUCT_LA)
TITLES = _set(TITLES_AR, TITLES_LA)
LATIN_ENGLISH_TITLES = _set(ENGLISH_TITLES)
WEAK = _set(WEAK_AR, WEAK_LA)
RELATION = _set(RELATION_AR)
NOT_WEAK = _set(*NOT_AFTER_WEAK)
