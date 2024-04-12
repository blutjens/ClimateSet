import wandb
from hydra.utils import instantiate as hydra_instantiate
from omegaconf import DictConfig

import pytorch_lightning as pl
from pytorch_lightning import seed_everything

import emulator.src.utils.config_utils as cfg_utils
from emulator.src.utils.interface import get_model_and_data
from emulator.src.utils.utils import get_logger
from pytorch_lightning.profilers import PyTorchProfiler
from datetime import datetime
from torch.profiler import profile, record_function, ProfilerActivity
from codecarbon import EmissionsTracker



def run_model(config: DictConfig):
    seed_everything(config.seed, workers=True)
    log = get_logger(__name__)
    log.info("In run model")
    cfg_utils.extras(config)

    log.info("Running model")
    if config.get("print_config"):
        cfg_utils.print_config(config, fields="all")


    
    emulator_model, data_module = get_model_and_data(config)
    log.info(f"Got model - {config.name}")
    c = datetime.now()
    # Displays Time
    current_time = c.strftime('%H:%M:%S')

    profiler = None
    if config.get("pyprofile"):
        profiler = PyTorchProfiler(dirpath="logs/profiles",filename=f"Basetest-{config.name}-Basetest-{current_time}",activities=[ProfilerActivity.CPU],
            profile_memory=True, record_shapes=True)
        
    log.info(config.name)

    # Init Lightning callbacks and loggers
    callbacks = cfg_utils.get_all_instantiable_hydra_modules(config, "callbacks")
    loggers = cfg_utils.get_all_instantiable_hydra_modules(config, "logger")
    
    # Init Lightning trainer
    trainer: pl.Trainer = hydra_instantiate(
        config.trainer,
        profiler=profiler,
        callbacks=callbacks,
        logger=loggers,  # , deterministic=True
    )

    # Send some parameters from config to all lightning loggers
    log.info("Logging hyperparameters to the PyTorch Lightning loggers.")
    cfg_utils.log_hyperparameters(
        config=config,
        model=emulator_model,
        data_module=data_module,
        trainer=trainer,
        callbacks=callbacks,
    )
    
    tracker = EmissionsTracker()
    tracker.start()
    trainer.fit(model=emulator_model, datamodule=data_module)
    emissions: float = tracker.stop()
    log.info(f"Total emissions: {emissions} kg")

    cfg_utils.save_emissions_to_wandb(config, emissions)
    cfg_utils.save_hydra_config_to_wandb(config)

    # Testing:
    if config.get("test_after_training"):
        trainer.test(datamodule=data_module, ckpt_path="best")

    if config.get("logger") and config.logger.get("wandb"):
        wandb.finish()

    # log.info("Reloading model from checkpoint based on best validation stat.")
    # final_model = emulator_model.load_from_checkpoint(trainer.checkpoint_callback.best_model_path,
    #    datamodule_config=config.datamodule, output_normalizer=data_module.normalizer.output_normalizer)
    # return final_model
