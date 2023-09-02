# 🧠 Geniusrise
# Copyright (C) 2023  geniusrise.ai
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import os
from abc import abstractmethod
from typing import Dict, Optional

import numpy as np
from datasets import Dataset, DatasetDict
from geniusrise import BatchInput, BatchOutput, Bolt, State
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from transformers import (
    EvalPrediction,
    Trainer,
    TrainingArguments,
)


class HuggingFaceFineTuner(Bolt):
    """
    A bolt for fine-tuning Hugging Face models.

    This bolt uses the Hugging Face Transformers library to fine-tune a pre-trained model.
    It uses the `Trainer` class from the Transformers library to handle the training.
    """

    def __init__(
        self,
        input: BatchInput,
        output: BatchOutput,
        state: State,
        **kwargs,
    ) -> None:
        """
        Initialize the bolt.

        Args:
            input (BatchInput): The batch input data.
            output (OutputConfig): The output data.
            state (State): The state manager.
            **kwargs: Additional keyword arguments.
        """
        super().__init__(
            input=input,
            output=output,
            state=state,
        )
        super().__init__(input=input, output=output, state=state)
        self.input = input
        self.output = output
        self.state = state

        self.model_name: Optional[str] = None
        self.tokenizer_name: Optional[str] = None
        self.model_class: Optional[str] = None
        self.tokenizer_class: Optional[str] = None
        self.eval: bool = False

        self.tokenizer = None
        self.model = None
        self.train_dataset = None
        self.eval_dataset = None

        self.log = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def load_dataset(self, dataset_path: str, **kwargs) -> Dataset | DatasetDict | Optional[Dataset]:
        """
        Load a dataset from a file.

        Args:
            dataset_path (str): The path to the dataset file.
            **kwargs: Additional keyword arguments to pass to the `load_dataset` method.

        Returns:
            Dataset: The loaded dataset.

        Raises:
            NotImplementedError: This method should be overridden by subclasses.
        """
        raise NotImplementedError("Subclasses should implement this!")

    def preprocess_data(self):
        """Load and preprocess the dataset"""
        try:
            self.input.copy_from_remote()
            train_dataset_path = os.path.join(self.input.get(), "train")
            eval_dataset_path = os.path.join(self.input.get(), "eval")
            self.train_dataset = self.load_dataset(train_dataset_path)
            if self.eval:
                self.eval_dataset = self.load_dataset(eval_dataset_path)
        except Exception as e:
            self.log.error(f"Failed to preprocess data: {e}")
            raise

    def load_models(self):
        """Load the model and tokenizer"""
        try:
            if self.model_name.lower() == "local":
                self.model = getattr(__import__("transformers"), str(self.model_class)).from_pretrained(
                    os.path.join(self.input.get(), "/model")
                )
            else:
                self.model = getattr(__import__("transformers"), str(self.model_class)).from_pretrained(self.model_name)

            if self.tokenizer_name.lower() == "local":
                self.tokenizer = getattr(__import__("transformers"), str(self.tokenizer_class)).from_pretrained(
                    os.path.join(self.input.get(), "/model")
                )
            else:
                self.tokenizer = getattr(__import__("transformers"), str(self.tokenizer_class)).from_pretrained(
                    self.tokenizer_name
                )
        except Exception as e:
            self.log.error(f"Failed to load model: {e}")
            raise

    def upload_to_hf_hub(self):
        """Upload the model and tokenizer to Hugging Face Hub.

        Args:
            repo_name (str): The repository name on Hugging Face Hub.
            organization (str, optional): The organization name if uploading to an organization. Defaults to None.
            private (bool, optional): Whether to make the repository private. Defaults to False.
        """
        try:
            if self.model:
                self.model.push_to_hub(
                    repo_id=self.hf_repo_id,
                    commit_message=self.hf_commit_message,
                    token=self.hf_token,
                    private=self.hf_private,
                    create_pr=self.hf_create_pr,
                )
            if self.tokenizer:
                self.tokenizer.push_to_hub(
                    repo_id=self.hf_repo_id,
                    commit_message=self.hf_commit_message,
                    token=self.hf_token,
                    private=self.hf_private,
                    create_pr=self.hf_create_pr,
                )
        except Exception as e:
            self.log.error(f"Failed to upload model to huggingface hub: {e}")
            raise

    def compute_metrics(self, eval_pred: EvalPrediction) -> Optional[Dict[str, float]] | Dict[str, float]:
        """
        Compute metrics for evaluation.

        Args:
            eval_pred (EvalPrediction): The evaluation predictions.

        Returns:
            dict: The computed metrics.
        """
        predictions, labels = eval_pred
        predictions = np.argmax(predictions, axis=1)

        return {
            "accuracy": accuracy_score(labels, predictions),
            "precision": precision_recall_fscore_support(labels, predictions, average="binary")[0],
            "recall": precision_recall_fscore_support(labels, predictions, average="binary")[1],
            "f1": precision_recall_fscore_support(labels, predictions, average="binary")[2],
        }

    def fine_tune(
        self,
        model_name: str,
        tokenizer_name: str,
        num_train_epochs: int,
        per_device_train_batch_size: int,
        model_class: str = "AutoModel",
        tokenizer_class: str = "AutoTokenizer",
        eval: bool = False,
        hf_repo_id: Optional[str] = None,
        hf_commit_message: Optional[str] = None,
        hf_token: Optional[str] = None,
        hf_private: bool = True,
        hf_create_pr: bool = False,
        **kwargs,
    ):
        """
        Fine-tune the model.

        Args:
            model (PreTrainedModel): The pre-trained model to fine-tune.
            tokenizer (PreTrainedTokenizer): The tokenizer associated with the model.
            output_dir (str): The output directory where the model predictions and checkpoints will be written.
            num_train_epochs (int): Total number of training epochs to perform.
            per_device_train_batch_size (int): Batch size per device during training.
            eval (bool, optional): Whether to evaluate the model after training. Defaults to False.
            **kwargs: Additional keyword arguments for training.

        Raises:
            FileNotFoundError: If the output directory does not exist.
        """
        try:
            self.model_name = model_name
            self.tokenizer_name = tokenizer_name
            self.output_dir = self.output.output_folder
            self.num_train_epochs = num_train_epochs
            self.per_device_train_batch_size = per_device_train_batch_size
            self.model_class = model_class
            self.tokenizer_class = tokenizer_class
            self.eval = eval
            self.hf_repo_id = hf_repo_id
            self.hf_commit_message = hf_commit_message
            self.hf_token = hf_token
            self.hf_private = hf_private
            self.hf_create_pr = hf_create_pr

            # Load model and tokenizer
            self.load_models()

            # Load dataset
            self.preprocess_data()

            training_args = TrainingArguments(
                output_dir=os.path.join(self.output_dir, "model"),
                num_train_epochs=num_train_epochs,
                per_device_train_batch_size=per_device_train_batch_size,
                **kwargs,
            )

            trainer = Trainer(
                model=self.model,
                args=training_args,
                train_dataset=self.train_dataset,
                eval_dataset=self.eval_dataset if self.eval else None,
                tokenizer=self.tokenizer,
                compute_metrics=self.compute_metrics,
            )

            trainer.train()
            trainer.save_model()

            if self.eval:
                eval_result = trainer.evaluate()
                self.log.info(f"Evaluation results: {eval_result}")

            if self.hf_repo_id:
                self.upload_to_hf_hub()
        except Exception as e:
            self.log.error(f"Failed to fine tune model: {e}")
            self.state.set_state(self.id, {"success": False, "exception": str(e)})
            raise
        self.state.set_state(self.id, {"success": True})
