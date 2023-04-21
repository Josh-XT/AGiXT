import { useState, useEffect } from "react";
import {
    Typography,
    Paper,
    TextField,
    Button,
} from "@mui/material";
import axios from "axios";
import { useRouter } from "next/router";
import useSWR from "swr";
export default function AgentObjective() {
    const [running, setRunning] = useState(false);
    const [objective, setObjective] = useState("");
    const agentName = useRouter().query.agent;

    const taskStatus = useSWR(`agent/${agentName}/task`, async () => (running ? (await axios.get(`${process.env.API_URI ?? 'http://localhost:5000'}/api/task/output/${agentName}`)).data : null), { refreshInterval: 3000 });
    useEffect(() => {
        queryRunning();
    }, [])
    const queryRunning = async () => {
        setRunning((await axios.get(`${process.env.API_URI ?? 'http://localhost:5000'}/api/agent/${agentName}/task/status`)).data.status);
    }

    const toggleRunning = async (objective) => {
        if (running) {
            await axios.delete(`${process.env.API_URI ?? 'http://localhost:5000'}/api/agent/${agentName}/task`);
        }
        else {
            await axios.post(`${process.env.API_URI ?? 'http://localhost:5000'}/api/agent/${agentName}/task`, { objective: objective });
        }
        await queryRunning();
        mutate("agents");
    };

    return (
        <>
            <TextField

                label="Agent Objective"
                value={objective}
                onChange={(e) => setObjective(e.target.value)}
                sx={{ mb: 2 }}
                fullWidth
            />
            <Button
                variant="contained"
                color="primary"
                onClick={toggleRunning}
                fullWidth
            >
                {running ? "Stop" : "Start"} Pursuing Objective
            </Button>

            {
                taskStatus.data ?
                    <>
                        <Typography sx={{ mt: "1rem" }} variant="h6" gutterBottom>
                            Objective Work Log
                        </Typography>
                        <Paper
                            elevation={3}
                            sx={{ flexGrow: 1, padding: "0.5rem", overflowY: "auto" }}
                        >
                            {taskStatus.data.map((message, index) => (
                                <pre key={index} style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                                    {message}
                                </pre>
                            ))}
                        </Paper>
                    </>
                    : null
            }
        </>
    );
};
