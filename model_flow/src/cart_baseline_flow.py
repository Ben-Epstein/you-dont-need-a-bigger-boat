"""

    Baseline implemented using Metaflow

"""

# Load env variables
try:
    from dotenv import load_dotenv
    load_dotenv('.env')
except Exception as e:
    print(e)

import os
from metaflow import FlowSpec, step, batch, current, environment
from pip_decorator import pip

class CartFlow(FlowSpec):

    @step
    def start(self):
        """
        Create a random dataset.
        """
        print("flow name: %s" % current.flow_name)
        print("run id: %s" % current.run_id)
        print("username: %s" % current.username)

        self.next(self.prepare_dataset)

    @step
    def prepare_dataset(self):
        """
        Read in raw session data and build a labelled dataset for purchase/abandonment prediction
        """
        from prepare_dataset import prepare_dataset

        self.dataset = prepare_dataset(training_file=os.getenv('BROWSING_TRAIN_PATH'), K=300000)

        self.next(self.get_model_config)

    @step
    def get_model_config(self):
        '''
        Get model hyper-params;
        It is possible in this step perform a for-each to parallel run over a range of hyper params;
        '''
        from utils import return_json_file_content

        # read just a single configuration
        self.config = return_json_file_content(os.getenv('MODEL_CONFIG_PATH'))
        self.next(self.train_model)



    @batch(gpu=1, cpu=8, image='763104351884.dkr.ecr.us-east-1.amazonaws.com/tensorflow-training:2.3.1-gpu-py37-cu110-ubuntu18.04')
    @environment(vars={'WANDB_API_KEY': os.getenv('WANDB_API_KEY')})
    @pip(libraries={'wandb': '0.10.30'})
    @step
    def train_model(self):
        """
        Train a regression model on the random dataset, on GPU.
        """
        import wandb
        from model import train_lstm_model

        assert os.getenv('WANDB_API_KEY')

        wandb.init(project="cart-abandonment",
                   id=current.run_id,
                   config=self.config,
                   resume='allow',
                   reinit=True)

        self.model, self.model_weights = train_lstm_model(x=self.dataset['X'],
                                                          y=self.dataset['y'],
                                                          epochs=self.config['EPOCHS'],
                                                          patience=self.config['PATIENCE'],
                                                          lstm_dim=self.config['LSTM_DIMS'],
                                                          batch_size=self.config['BATCH_SIZE'],
                                                          lr=self.config['LEARNING_RATE'])
        self.next(self.make_predictions)

    @step
    def make_predictions(self):
        from model import make_predictions
        self.predictions = make_predictions(model=self.model,
                                            model_weights=self.model_weights,
                                            test_file=os.getenv('INTENT_TEST_PATH'))
        print('First 5 predictions...')
        print(self.predictions[:5])
        self.next(self.end)

    @step
    def end(self):
        """
        DAG is done!
        """
        print('DAG ended!')


if __name__ == '__main__':
    CartFlow()