try:
    import google.generativeai as genai  # Primary import attempt
except ImportError:
    import sys
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "google.generativeai"])
    import google.generativeai as genai  # Import again after installation

class GeminiProvider:
    def __init__(self, 
                 GOOGLE_API_KEY: str, 
                 AI_MODEL: str = "gemini-pro",
                 MAX_TOKENS: int = 4000,
                 AI_TEMPERATURE: float = 0.7,
                 **kwargs):

        self.requirements = ["google.generativeai"]  
        self.GOOGLE_API_KEY =  GOOGLE_API_KEY
        self.AI_MODEL = AI_MODEL
        self.MAX_TOKENS = MAX_TOKENS
        self.AI_TEMPERATURE = AI_TEMPERATURE

        # Configure and setup Gemini model
        genai.configure(api_key=self.GOOGLE_API_KEY)
        self.model = genai.GenerativeModel(self.AI_MODEL)

    async def inference(self, prompt, tokens: int = 0):
        try:
            # *** ADJUST BASED ON GEMINI API ***
            new_max_tokens = int(self.MAX_TOKENS) - tokens   
            response = self.model.generate(  # Replace 'generate' if needed
                prompt=prompt, 
                temperature=float(self.AI_TEMPERATURE),
                max_output_tokens=new_max_tokens
            )

            # *** ADJUST BASED ON GEMINI RESPONSE STRUCTURE ***
            return response.text

        except Exception as e:
            return f"Gemini Error: {e}"

