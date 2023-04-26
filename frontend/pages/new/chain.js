
import axios from 'axios';
import { useState } from 'react';
import { Container, TextField, Button, Typography } from '@mui/material';
import { mutate } from "swr"
import useSWR from 'swr';
import DoubleSidedMenu from '@/components/content/DoubleSidedMenu';
import ChainList from '@/components/chain/ChainList';
export default function Home() {
  const [name, setName] = useState("");
  const [chain, setChain] = useState("");
  const handleCreate = async () => {
    await axios.post(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/chain`, { chain_name: name, chain: chain });
    mutate("chain");
  }
  const chains = useSWR('chain', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/chain`)).data);
  return <DoubleSidedMenu title={"Add a New Chain"} leftHeading={"Chains"} leftSWR={chains} leftMenu={ChainList} rightHeading={null} rightSWR={null} rightMenu={null} content={() => <Container>
    <Typography variant='h6' component='h2' marginY={"1rem"}>
      Add a New Chain
    </Typography>
   <form>
    <TextField fullWidth variant="outlined" label="Chain Name" value={name} onChange={(e) => {setName(e.target.value)}} />
    <TextField fullWidth variant="outlined" label="Chain Body" multiline rows={50} value={chain} onChange={(e) => {setChain(e.target.value)}} />
    <Button variant="contained" color="primary" onClick={handleCreate} sx={{marginY: "1rem"}}>Add a New Chain</Button>
   </form>
  </Container>} />;
}
