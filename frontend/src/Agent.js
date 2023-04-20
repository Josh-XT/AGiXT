import { URIContext } from "./App";

const Agent = (props) => {
    [refresh, setRefresh] = useState(null);
    [agentData, setAgentData] = useState(null);
    const baseURI = useContext(URIContext);
    const toggleRunning = () => {
        if (refresh) {
            try
            {
                fetch(`${baseURI}/api/task/stop/${props.agent}`, { method: "POST" }).then(() => {
                    clearInterval(refresh);
                    setRefresh(null);
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
                }).then(() => {
                    setRefresh(
                        setInterval(async () => {
                            const response = await ((await fetch(`${baseURI}/api/task/output/${props.agent}`)).json());
                            console.log(response);
                            if (response.output && response.output.length > 0) setAgentData(response.output);
                        }, 3000)
                    );
                })
            }
            catch(error) {
                console.error("Error Starting Agent:\n",error);
            }

        }
    }
    return (
        <>
            <Grid item xs={6} sx={props.hidden ? { visibility: "hidden" } : {}}>
                <AgentControl {...props} toggleRunning={toggleRunning} data={agentData} />
            </Grid>
            <Grid item xs={3} sx={props.hidden ? { visibility: "hidden" } : {}}>
                <AgentCommands {...props} />
            </Grid>
        </>
    );
};

export default Agent;