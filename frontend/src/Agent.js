import { URIContext } from "./App";
import { useState, useContext, useEffect } from "react";
import AgentControl from "./AgentControl";
import AgentCommandList from "./AgentCommandList";
import {
  Grid
} from "@mui/material";
import { LoadingContext } from "./App";
const Agent = (props) => {
    const [refresh, setRefresh] = useState();
    const [agentData, setAgentData] = useState(null);
    const [objective, setObjective] = useState("");
    const baseURI = useContext(URIContext);
    const [loading, setLoading] = useState(true);
    function toggleRunning() {
        if (refresh) {
            try
            {
                fetch(`${baseURI}/api/task/stop/${props.agent}`, { method: "POST" }).then(async () => {
                    if (!await(await fetch(`${baseURI}/api/task/status/${props.agent}`)).json().status)
                    {
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
                fetch(`${baseURI}/api/task/start/${props.agent}`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({ objective: objective }),
                }).then(async () => {
                    if (await(await fetch(`${baseURI}/api/task/status/${props.agent}`)).json().status)
                    {
                        setRefresh(
                            setInterval(async () => {
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