import { useRouter } from 'next/router';
import axios from 'axios';
import useSWR from 'swr';
import PromptPanel from './PromptPanel';
import PopoutDrawerWrapper from '../../menu/PopoutDrawerWrapper';
import PromptList from './PromptList';
export default function PromptControl({ data }) {
    const promptName = useRouter().query.prompt;
    const prompts = useSWR('prompt', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/prompt`)).data.prompts);
    return <PopoutDrawerWrapper title={"Manage Prompt \""+promptName+"\""} leftHeading={"Prompts"} leftSWR={prompts} leftMenu={PromptList} rightHeading={null} rightSWR={null} rightMenu={null}>
        <PromptPanel />
    </PopoutDrawerWrapper>;
}


