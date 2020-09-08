#!/usr/bin/env python3
# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import kfp
from kfp import dsl


def print_op(msg):
  """Print a message."""
  return dsl.ContainerOp(
      name='Print',
      image='alpine:3.6',
      command=['echo', msg],
  )


@dsl.pipeline(
    name='Pipeline service account',
    description='The pipeline shows how to set the service account to use for the pipeline.'
)
def pipeline_service_account():
  op1 = print_op('hey, what are you up to?')
  op2 = print_op('train my model.')
  dsl.get_pipeline_conf().set_service_account_name("custom-pipeline-runner")

if __name__ == '__main__':
  kfp.compiler.Compiler().compile(transform_pipeline, __file__ + '.yaml')
