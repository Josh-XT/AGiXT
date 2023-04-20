import {
  Grid,
  Typography
} from "@mui/material";
import {useEffect, useState} from "react";

import ReactMarkdown from "react-markdown";
const AgentHome = (props) => {
    const [readme, setReadme] = useState("");
    useEffect(() => {
        fetch("https://raw.githubusercontent.com/Josh-XT/Agent-LLM/main/README.md").then(async (response) => {
            setReadme(await response.text());
        })
    }, []);
    return (
            <Grid item xs={9}>
                <Typography variant="h4" sx={{ textAlign: "center" }}>Welcome to Agent LLM</Typography>
                <ReactMarkdown>{readme}</ReactMarkdown>
            </Grid>
    );
};

export default AgentHome;