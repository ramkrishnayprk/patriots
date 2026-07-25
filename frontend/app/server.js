const express = require("express");
const fs = require("fs");
const axios = require("axios");
const path = require("path");
require("dotenv").config();

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, "public")));

// Load your scraped PhD-IT program content
const PHD_IT_CONTEXT = fs.readFileSync("phd_it_context.txt", "utf-8");

const OPENAI_URL = "https://api.openai.com/v1/chat/completions";
const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
const MODEL_NAME = "gpt-4o-mini";  // or whichever model your key has access to

if (!OPENAI_API_KEY) {
    console.error("Missing OPENAI_API_KEY. Set it in a .env file before starting the server.");
    process.exit(1);
}

app.post("/api/chat", async (req, res) => {
    const userMessage = req.body.message;

    if (!userMessage || !userMessage.trim()) {
        return res.status(400).json({ error: "Empty message" });
    }

    const systemPrompt = `You are an assistant that answers questions about a PhD in IT program.
Answer ONLY using the context provided below. If the answer isn't in the context, say you don't have that information.

Context:
${PHD_IT_CONTEXT}`;

    try {
        const response = await axios.post(
            OPENAI_URL,
            {
                model: MODEL_NAME,
                messages: [
                    { role: "system", content: systemPrompt },
                    { role: "user", content: userMessage }
                ],
                temperature: 0.3
            },
            {
                headers: {
                    Authorization: `Bearer ${OPENAI_API_KEY}`,
                    "Content-Type": "application/json"
                }
            }
        );

        const answer = response.data.choices[0].message.content;
        res.json({ response: answer });

    } catch (error) {
        if (error.response) {
            console.error("OpenAI API error:", error.response.status, error.response.data);
            return res.status(500).json({
                error: `OpenAI API error: ${error.response.data.error?.message || "Unknown error"}`
            });
        }

        console.error("Unexpected error:", error.message);
        res.status(500).json({ error: "Failed to get a response from the LLM." });
    }
});

const PORT = 5000;
app.listen(PORT, () => {
    console.log(`Chatbot running at http://localhost:${PORT}`);
});