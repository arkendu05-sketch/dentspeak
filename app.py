import base64
import streamlit as st
from sarvamai import SarvamAI

# 1. Connect to Sarvam (key comes from .streamlit/secrets.toml)
client = SarvamAI(api_subscription_key=st.secrets["SARVAM_API_KEY"])

LANGS = {"Tamil": "ta-IN", "Bengali": "bn-IN", "Hindi": "hi-IN", "English": "en-IN"}

SAMPLE = """Tooth 36: deep caries, close to pulp. Root canal treatment advised.
Tooth 48: impacted wisdom tooth. Extraction recommended.
Generalised gingivitis. Scaling advised. Review in 6 months."""

# 2. The page
st.title("🦷 DentSpeak")
st.caption("Your dental report, explained in your language.")

report = st.text_area("Paste the dental report", SAMPLE, height=150)
lang = st.selectbox("Language", list(LANGS.keys()))


# 3. Step one: explain the report simply (Sarvam chat model)
def explain(report, lang):
    prompt = f"""You are a kind dentist talking to a patient with no medical knowledge.
Explain this dental report in simple {lang}, in under 80 words.
No medical jargon. Say what each problem means and what the patient should do next.
Never say tooth numbers. Tooth numbers use the FDI system (for example, 36 means lower left first molar).
Describe each tooth's location in plain words, like "lower left back tooth".
End with one clear action, like booking a visit.

Report:
{report}"""
    response = client.chat.completions(
        model="sarvam-105b-conversations",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4000,
    )
    msg = response.choices[0].message
    if not msg.content:
        st.warning(f"Empty answer. Reason: {response.choices[0].finish_reason}")
    return msg.content


# 4. Step two: turn the explanation into speech (Bulbul)
def speak(text, lang_code):
    response = client.text_to_speech.convert(
        text=text,
       language_code=lang_code,
        model="bulbul:v3",
        speaker="shubh",
    )
    return base64.b64decode("".join(response.audios))


# 5. The button that runs both steps
if st.button("Explain and speak"):
    with st.spinner("Reading your report..."):
        explanation = explain(report, lang)

    if not explanation:
        st.error("No explanation came back. Try again.")
        st.stop()

    st.subheader("What this means")
    st.write(explanation)

    with st.spinner("Making audio..."):
        audio = speak(explanation, LANGS[lang])
    st.audio(audio, format="audio/wav")

st.caption("Demo only. Not medical advice. Always talk to your dentist.")


