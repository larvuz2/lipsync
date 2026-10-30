# Clip inventory: Drive folder `LIP SYNC TEST` (S01E01)

17 clips: 1920×1080 H.264, 23.976 fps, stereo 48 kHz AAC. Each `.mp3` is a copy of the clip's
own audio (full mix). File names share the prefix
`RISE_OF_THE_RAVEN_S01E01_INT_VERSION_ProRes4444_2160p25_200_SDR_OV20R128_MNE20_OV51R128_MNE51_First16_Splits`;
the table uses the number at the end.

How this was made:
- Hungarian text: Whisper large-v3, run locally. A native speaker should check it; lines marked `?` are uncertain.
- Who speaks: pitch analysis of each line plus the frames. I can't listen to the audio, so confirm by ear.
- Cuts: ffmpeg scene detection.

**Lip-sync column:** **Test** = chosen for the first tests · *Later* = lip-sync in the full run ·
*Audio only* = the speaker isn't visible, so dub the voice and leave the picture alone.

| Clip | Length | Cuts at | Picture | Hungarian (cleaned) → meaning | Voice | Speaker visible? | Lip-sync |
|---|---|---|---|---|---|---|---|
| 87434 | 3.9 s | – | Trainer (shirtless, braids), single face, profile turning to 3/4 | *Jankó, gyere ide!* → "Jankó, come here!" | Adult male (Trainer) | Yes | **Test 1** |
| 87646 | 3.4 s | – | The boy (Jankó) in profile, back of head; trainer's body enters | *Na, mutasd! Hogy tartod azt az íjat?* → "Come on, show me! How are you holding that bow?" | Trainer | No (off-screen) | Audio only |
| 87725 | 9.3 s | 2.29 | Boy drawing the bow, then wide on trainer + boy | *Az ideget tartsd távolabb, megüti az arcod.* → "Keep the string further out, it'll hit your face." / *Engedd lejjebb a vállad.* → "Drop your shoulder." | Trainer | Yes, small in the wide | *Later* |
| 88011 | 7.4 s | – | Extreme close-up: trainer's face behind the boy's, hand and bowstring near the trainer's mouth | *Ne a kezeddel célozz, ne is a szemeddel.* → "Don't aim with your hand, nor with your eyes." | Trainer | Yes, partly hidden | **Test 3** |
| 88186 | 5.5 s | – | Wide: trainer + boy | *Itt.* → "Here." | Trainer? | Yes, small | *Later* |
| 88514 | 4.9 s | 3.34 | Woman in blue dress on the stairs, far away | *Jankó, hányszor mondtam, hogy ne az udvaron játssz azzal az íjjal?* → "Jankó, how many times have I told you not to play with that bow in the yard?" | Adult female | Yes, tiny face | *Later* (low priority) |
| 88693 | 1.7 s | – | Trainer walking, face at the top edge | *Csináljátok!* → "Keep at it!" | Trainer? | Partly | *Later* |
| 89846 | 8.9 s | 2.09, 3.46, 5.21, 7.09 | Establishing shots, crowd running | Shouting: *Jönnek! … fegyverbe!* → "They're coming! To arms!" … *Mindenki a kapuhoz!* → "Everyone to the gate!" | Crowd / unseen | No | Audio only |
| 90058 | 9.5 s | 4.84, 6.67, 8.09 | Father (blue tunic) medium close-up, frontal → group with kids → boy close-up | *Szedd a lábad!* ? / *Ide figyeljetek! El kell bújnotok!* / *Bármi történik, azt teszitek, amit anyátok mond, megértettétek?* / boy: *Én maradok veled!* / off-screen: *Jankó!* | Father + boy + off-screen | Mixed | **Test 2** |
| 90482 | 5.5 s | 1.88 | Father wide, pointing; then father with boy, woman blurred in front | *Nyisd ki a kaput! Gyertek!* → "Open the gate! Come on!" / *Ide figyelj, a te dolgod most az, hogy ezt túléld!* → "Listen, your job now is to survive this!" | Shouting voice + father | Partly | *Later* |
| 90613 | 3.5 s | – | Father from behind; boy facing camera | *Hozd ide a karvédőmet ?, aztán azt csináld, amit anyád mond, megértetted?* → "Bring me my bracer, then do what your mother says, understood?" | Father | No (back to camera) | Audio only |
| 90694 | 2.7 s | 1.25 | Mother (curly hair, green cloak) → father close-up | *Nem lesz semmi baj. Minden rendben lesz.* → "It'll be all right. Everything will be fine." | Adult male (father) | Second shot only | *Later* |
| 90756 | 2.8 s | – | Mother with the little girl, medium shot | *Nézzetek már ki!* ? | ? | ? | Check by ear |
| 90909 | 3.2 s | – | Chaos, blurred, girl running | Shouting, unclear | Unseen | No | Audio only |
| 90983 | 3.6 s | 2.21, 3.42 | Wide skirmish → father close-up, shouting | *És most bújjatok!* → "Now hide!" / *Nyissátok ki!* → "Open it!" | Father | Yes at the end | *Later* (good shouting test) |
| 91067 | 2.6 s | 1.00 | Crowd, then the boy in the yard | *De uram, …* ? (unclear) | High voice | Unclear | Check by ear |
| 91128 | 1.5 s | – | Fight at the gate, hooded figures | *Vigyázz …* ? (unclear) | Unseen | No | Audio only |

## Speech per character in these clips (for voice cloning)

| Character (working name) | Voice | Approx. clean speech here | Enough for a good clone? |
|---|---|---|---|
| Trainer (shirtless, braids) | adult male, ~80–95 Hz | ~16 s over 6 clips | Usable for a test, weak for production |
| Father (blue tunic) | adult male, ~107 Hz | ~17 s over 5 clips | Usable for a test, weak for production |
| Jankó (the boy) | child, ~285 Hz | ~1–3 s | No |
| Mother / woman on the stairs | adult female, ~216 Hz | ~3 s | No |

ElevenLabs-style cloning does best with 1–2 minutes of clean, music-free speech per voice, so we
need more audio per character for the full run (see PLAN.md, "What I need from you").
