from DBConnection import session, Chain as ChainDB, ChainStep, ChainStepResponse


class Chain:
    def get_chain(self, chain_name):
        chain = (
            session.query(ChainStep)
            .join(ChainDB)
            .filter(ChainDB.name == chain_name)
            .all()
        )
        return chain

    def get_chains(self):
        chains = session.query(ChainDB).all()
        return [chain.name for chain in chains]

    def add_chain(self, chain_name):
        chain = ChainDB(name=chain_name)
        session.add(chain)
        session.commit()

    def rename_chain(self, chain_name, new_name):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()
        chain.name = new_name
        session.commit()

    def add_chain_step(self, chain_name, step_number, agent_name, prompt_type, prompt):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()
        chain_step = ChainStep(
            chain_id=chain.id,
            step_number=step_number,
            agent_name=agent_name,
            prompt_type=prompt_type,
            prompt=prompt,
        )
        session.add(chain_step)
        session.commit()

    def update_step(self, chain_name, step_number, agent_name, prompt_type, prompt):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()
        chain_step = (
            session.query(ChainStep)
            .filter(
                ChainStep.chain_id == chain.id, ChainStep.step_number == step_number
            )
            .first()
        )
        chain_step.agent_name = agent_name
        chain_step.prompt_type = prompt_type
        chain_step.prompt = prompt
        session.commit()

    def delete_step(self, chain_name, step_number):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()
        chain_step = (
            session.query(ChainStep)
            .filter(
                ChainStep.chain_id == chain.id, ChainStep.step_number == step_number
            )
            .first()
        )
        session.delete(chain_step)
        session.commit()

    def delete_chain(self, chain_name):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()
        session.delete(chain)
        session.commit()

    def get_step(self, chain_name, step_number):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()
        chain_step = (
            session.query(ChainStep)
            .filter(
                ChainStep.chain_id == chain.id, ChainStep.step_number == step_number
            )
            .first()
        )
        return chain_step

    def get_steps(self, chain_name):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()
        chain_steps = (
            session.query(ChainStep)
            .filter(ChainStep.chain_id == chain.id)
            .order_by(ChainStep.step_number)
            .all()
        )
        return chain_steps

    def move_step(self, chain_name, current_step_number, new_step_number):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()
        chain_step = (
            session.query(ChainStep)
            .filter(
                ChainStep.chain_id == chain.id,
                ChainStep.step_number == current_step_number,
            )
            .first()
        )
        chain_step.step_number = new_step_number
        if new_step_number < current_step_number:
            session.query(ChainStep).filter(
                ChainStep.chain_id == chain.id,
                ChainStep.step_number >= new_step_number,
                ChainStep.step_number < current_step_number,
            ).update(
                {"step_number": ChainStep.step_number + 1}, synchronize_session=False
            )
        else:
            session.query(ChainStep).filter(
                ChainStep.chain_id == chain.id,
                ChainStep.step_number > current_step_number,
                ChainStep.step_number <= new_step_number,
            ).update(
                {"step_number": ChainStep.step_number - 1}, synchronize_session=False
            )
        session.commit()

    def get_step_response(self, chain_name, step_number="all"):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()
        if step_number == "all":
            chain_steps = (
                session.query(ChainStep)
                .filter(ChainStep.chain_id == chain.id)
                .order_by(ChainStep.step_number)
                .all()
            )
            responses = {}
            for step in chain_steps:
                chain_step_responses = (
                    session.query(ChainStepResponse)
                    .filter(ChainStepResponse.chain_step_id == step.id)
                    .order_by(ChainStepResponse.timestamp)
                    .all()
                )
                step_responses = [response.content for response in chain_step_responses]
                responses[str(step.step_number)] = step_responses
            return responses
        else:
            chain_step = (
                session.query(ChainStep)
                .filter(
                    ChainStep.chain_id == chain.id, ChainStep.step_number == step_number
                )
                .first()
            )
            if chain_step:
                chain_step_responses = (
                    session.query(ChainStepResponse)
                    .filter(ChainStepResponse.chain_step_id == chain_step.id)
                    .order_by(ChainStepResponse.timestamp)
                    .all()
                )
                return [response.content for response in chain_step_responses]
            else:
                return []

    def get_chain_responses(self, chain_name):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()
        chain_steps = (
            session.query(ChainStep)
            .filter(ChainStep.chain_id == chain.id)
            .order_by(ChainStep.step_number)
            .all()
        )
        responses = {}
        for step in chain_steps:
            chain_step_responses = (
                session.query(ChainStepResponse)
                .filter(ChainStepResponse.chain_step_id == step.id)
                .order_by(ChainStepResponse.timestamp)
                .all()
            )
            step_responses = [response.content for response in chain_step_responses]
            responses[str(step.step_number)] = step_responses
        return responses
