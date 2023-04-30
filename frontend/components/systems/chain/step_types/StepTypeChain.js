import { Select, MenuItem, TextField } from "@mui/material";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/router";
import axios from "axios";
import { mutate } from "swr";
import useSWR from "swr";
export default function StepTypeCommand({prompt}) {
    const [chain, setChain] = useState(-1);
    // TODO: Get commands directly from API without going through agent.
    const chains = useSWR('chain', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/chain`)).data);
    useEffect(() => {
        const chain = prompt.slice(11, indexOf(")"));
        setChain(chains.data&&prompt?chains.data.findIndex((chainName) => chainName == chain):-1);
    }, [chains.data, prompt]);
    return <>
        <Select label="Chain" sx={{ mx: "0.5rem" }} value={chain} onChange={(e) => setChain(e.target.value)}>
            <MenuItem value={-1}>Select a Chain...</MenuItem>
            {chains?.data?.map((chain, index) => {
                return <MenuItem key={index} value={index}>{chain}</MenuItem>;
            })}
        </Select>
    </>;
}