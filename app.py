import base64
import html
import io
import os
import re
import tempfile
import zipfile

import streamlit as st
from sarvamai import SarvamAI

# 0. Page setup: centered layout reads well on phones
st.set_page_config(page_title="DentSpeak", page_icon="🦷", layout="centered")

# 1. Simple password gate, so strangers can't use your Sarvam credits
if "ok" not in st.session_state:
    st.session_state.ok = False

if not st.session_state.ok:
    st.title("🦷 DentSpeak")
    pw = st.text_input("Enter access code", type="password")
    if st.button("Enter", use_container_width=True):
        if pw == st.secrets["APP_PASSWORD"]:
            st.session_state.ok = True
            st.rerun()
        else:
            st.error("Wrong code.")
    st.stop()

# 2. Connect to Sarvam
client = SarvamAI(api_subscription_key=st.secrets["SARVAM_API_KEY"])

LANGS = {"Bengali": "bn-IN", "Tamil": "ta-IN", "Hindi": "hi-IN", "English": "en-IN"}

SAMPLE = """Tooth 36: deep caries, close to pulp. Root canal treatment advised.
Tooth 48: impacted wisdom tooth. Extraction recommended.
Generalised gingivitis. Scaling advised. Review in 6 months."""

# 3. Two modes, each with its own instructions
PROMPTS = {
    "Dental report": """You are a kind dentist talking to a patient with no medical knowledge.
Explain this dental report in simple {lang}, in under 80 words.
No medical jargon. Say what each problem means and what the patient should do next.
Never say tooth numbers. Tooth numbers use the FDI system (for example, 36 means lower left first molar).
Describe each tooth's location in plain words, like "lower left back tooth".
End with one clear action, like booking a visit.""",

    "Prescription": """You are a careful pharmacist talking to a patient with no medical knowledge.
For each medicine in this prescription, say in simple {lang}:
what it is for, when to take it, and for how long, exactly as written.
If any medicine name, dose, or timing is unclear or missing, say clearly that you cannot read it
and the patient must check with their pharmacist. Never guess a medicine name or dose.
Never suggest changing a dose. Keep it under 120 words.
End by telling the patient to confirm with their pharmacist before taking any medicine.""",
}


# 4a. Remove HTML tags from the photo text so people can read it
def clean(text):
    text = re.sub(r"</(td|th)>", " ", text)
    text = re.sub(r"<br\s*/?>|</(tr|p|div|li|h\d)>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    lines = [l.strip() for l in text.splitlines()]
    return "\n".join(l for l in lines if l)


# 4. Read text from a photo (Sarvam Document Intelligence)
def read_document(photo):
    ext = os.path.splitext(photo.name)[1].lower() or ".jpg"
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "upload" + ext)
        with open(path, "wb") as f:
            f.write(photo.getvalue())

        job = client.document_intelligence.create_job(language="en-IN", output_format="md")
        job.upload_file(path)
        job.start()
        job.wait_until_complete(timeout=120)
        out = job.download_output(os.path.join(tmp, "result"))

        with open(out, "rb") as f:
            data = f.read()

    # The result can come back as a ZIP. If so, pull the text file out of it.
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            texts = [z.read(n).decode("utf-8", "ignore")
                     for n in z.namelist() if n.endswith((".md", ".txt", ".html"))]
        return "\n".join(texts)
    return data.decode("utf-8", "ignore")


# 5. Explain the text simply (Sarvam chat model)
def explain(text, lang, mode):
    prompt = PROMPTS[mode].format(lang=lang) + f"\n\nDocument:\n{text}"
    response = client.chat.completions(
        model="sarvam-105b-conversations",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4000,
    )
    return response.choices[0].message.content


# 5b. Translate the English explanation (Sarvam Translate)
def translate(text, lang_code):
    if lang_code == "en-IN":
        return text
    response = client.text.translate(
        input=text,
        source_language_code="en-IN",
        target_language_code=lang_code,
        model="sarvam-translate:v1",
    )
    return response.translated_text


# 6. Turn the explanation into speech (Bulbul)
def speak(text, lang_code):
    response = client.text_to_speech.convert(
        text=text,
        language_code=lang_code,
        model="bulbul:v3",
        speaker="shubh",
    )
    return base64.b64decode("".join(response.audios))


# 7. The page
st.title("🦷 DentSpeak")
st.caption("Your dental report or prescription, explained in your language.")

mode = st.radio("What do you have?", list(PROMPTS.keys()), horizontal=True)
lang = st.selectbox("Language", list(LANGS.keys()))

# On a phone, this button also offers "take photo" with the camera
photo = st.file_uploader("Take or upload a photo", type=["png", "jpg", "jpeg"])
if mode == "Prescription":
    st.info("Works best with printed prescriptions. Handwritten ones may be misread. Always check the text box.")

if "text" not in st.session_state:
    st.session_state.text = SAMPLE

if photo and st.button("Read photo", use_container_width=True):
    with st.spinner("Reading the photo... (can take 20-40 seconds)"):
        try:
            st.session_state.text = clean(read_document(photo))
        except Exception as e:
            st.error(f"Could not read the photo: {e}")

# The patient (or doctor) can see and correct what was read before explaining
text = st.text_area("Text to explain (check it, fix any mistakes)",
                    key="text", height=160)

# 8. One big button, easy to tap on a phone
if st.button("Explain and speak", type="primary", use_container_width=True):
    if not text.strip():
        st.warning("Nothing to explain yet.")
        st.stop()

    with st.spinner("Explaining..."):
        english = explain(text, "English", mode)

    if not english:
        st.error("No explanation came back. Try again.")
        st.stop()

    with st.spinner(f"Translating to {lang}..."):
        explanation = translate(english, LANGS[lang])

    if not explanation:
        st.error("No explanation came back. Try again.")
        st.stop()

    with st.spinner("Making audio..."):
        audio = speak(explanation, LANGS[lang])

    st.audio(audio, format="audio/wav")
    st.subheader("What this means")
    st.write(explanation)
    if lang != "English":
        with st.expander("English version (for doctors to check)"):
            st.write(english)

st.caption("Demo only. Not medical advice. Always talk to your dentist or pharmacist.")

