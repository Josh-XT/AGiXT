
import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/router";
import axios from "axios";
import { mutate } from "swr";
import useSWR from "swr";
import {
    Typography,
    Paper,
    TextField,
    Button,
} from "@mui/material";
export default function AgentObjective() {
    const [running, setRunning] = useState(false);
    const [objective, setObjective] = useState("");
    const agentName = useRouter().query.agent;
    const taskStatus = useSWR(`agent/${agentName}/task`, async () => (running ? (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/agent/${agentName}/task`)).data.output.split("\n") : null), { refreshInterval: running?3000:0, revalidateOnFocus: false });
    const queryRunning = useCallback(async () => {
        setRunning((await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/agent/${agentName}/task/status`)).data.status, {objective: objective});
    }, [agentName, objective]);
    useEffect(() => {
        queryRunning();
    }, [queryRunning])

    const toggleRunning = async () => {
        if (running) {
            await axios.post(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/agent/${agentName}/task`, {objective: "" });
        }
        else {
            await axios.post(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/agent/${agentName}/task`, { objective: objective });
        }
        await queryRunning();
        mutate("agents");
    };
    console.log(taskStatus.data);
    return (
        <>
            <TextField
                label="Enter Objective for Agent"
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
                            elevation={5}
                            sx={{ padding: "0.5rem", overflowY: "auto", height: "60vh" }}
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
