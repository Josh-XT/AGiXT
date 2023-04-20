import { URIContext } from "./App";
import { useState, useContext, useEffect } from "react";
import AgentControl from "./AgentControl";
import AgentCommandList from "./AgentCommandList";
import {
  Grid
} from "@mui/material";
import { LoadingContext } from "./App";
const Agent = (props) => {
    const [refresh, setRefresh] = useState(null);
    const [agentData, setAgentData] = useState(null);
    const [objective, setObjective] = useState("");
    const baseURI = useContext(URIContext);
    const [loading, setLoading] = useState(true);
    function toggleRunning() {
        console.log(refresh);
        console.log("Toggling Agent [Agent.js]");
        if (refresh) {
            try
            {
                console.log("Stopping Agent [Agent.js]");
                fetch(`${baseURI}/api/task/stop/${props.agent}`, { method: "POST" }).then(async () => {
                    console.log("Fetched [Agent.js]");
                    if (!await(await fetch(`${baseURI}/api/task/status/${props.agent}`)).json().status)
                    {
                        console.log("Stopped [Agent.js]");
                        clearInterval(refresh);
                        setRefresh(null);
                    }
                    else throw "Responded with successful stop, but the agent is still running.";                   
                })
            }
            catch(error) {
                console.error("Error Stopping Agent:\n",error);
            }

        } else {
            try {
                console.log("Starting Agent [Agent.js]");
                fetch(`${baseURI}/api/task/start/${props.agent}`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({ objective: objective }),
                }).then(async () => {
                    console.log("Fetched [Agent.js]");
                    if (await(await fetch(`${baseURI}/api/task/status/${props.agent}`)).json().status)
                    {
                        console.log("Started [Agent.js]");
                        setRefresh(
                            setInterval(async () => {
                                console.log("Updating (Interval) [Agent.js]");
                                const response = await ((await fetch(`${baseURI}/api/task/output/${props.agent}`)).json());
                                console.log(response);
                                if (response.output && response.output.length > 0) setAgentData(response.output);
                            }, 3000)
                        );
                    }
                    else throw "Responded with successful start, but the agent is not running."
                })
            }
            catch(error) {
                console.error("Error Starting Agent:\n",error);
            }

        }
    }
    useEffect(() => {
        fetch(`${baseURI}/api/task/status/${props.agent}`).then((agent) => agent.json()).then((agent) => {if(agent.status) toggleRunning();});
        setLoading(false);
    }, []);
    return (
        loading? <></> :
        <>
            <Grid item xs={6}>
                <AgentControl {...props} running={Boolean(refresh)} toggleRunning={toggleRunning} data={agentData??[]} objective={objective} setObjective={setObjective} />
            </Grid>
            <Grid item xs={3}>
                <AgentCommandList {...props} />
            </Grid>
        </>
    );
};

export default Agent;